
"""
Pulling SMART data from OSD
"""

import json
from mgr_module import MgrModule, CommandResult
import rados
from threading import Event
from datetime import datetime, timedelta, date, time

TIME_FORMAT = '%Y%m%d-%H%M%S'
SCRAPE_FREQUENCY = 86400  # seconds

# TODO maybe have a 'refresh' command to run after config-key set
# to wake the sleep interval
# TODO document


class Module(MgrModule):
    COMMANDS = [
        {
            "cmd": "smart status",
            "desc": "Show smart status",
            "perm": "r",
        },
        {
            "cmd": "smart on",
            "desc": "Enable automatic SMART scraping",
            "perm": "rw",
        },
        {
            "cmd": "smart off",
            "desc": "Disable automatic SMART scraping",
            "perm": "rw",
        },
        {
            "cmd": "osd smart scrape "
                   "name=osd_id,type=CephString,req=true",
            "desc": "Scraping SMART data of osd<osd_id>",
            "perm": "r"
        },
        {
            "cmd": "osd smart scrape-all",
            "desc": "Scraping SMART data of all OSDs",
            "perm": "r"
        },
        {
            "cmd": "osd smart dump "
                   "name=obj_name,type=CephString,req=true",
            "desc": "Get SMART data of osd_id, which was scraped and stored in a rados object",
            "perm": "r"
        },
        {
            "cmd": "osd smart dump-all",
            "desc": "Get SMART data of all OSDs, which was scraped and stored in a rados object",
            "perm": "r"
        },
        {
            "cmd": "smart predict-failure",
            "desc": "Run a failure prediction model based on the latest SMART stats.",
            "perm": "rw",
        },
        {
            "cmd": "smart warn",
            "desc": "Test warning.",
            "perm": "rw",
        },
    ]
    active = False
    run = True
    event = Event()
    # pool_name (check if it makes sense to leave here?)
    # scrape_frequency = SCRAPE_FREQUENCY
    # failure_prediction_action = 'warn'
    # failure_prediction_model = 'trivial'
    # last_scrape = 000000
    # dump_data = {}

    def open_connection(self):
        # TODO check that pool name is actually configurable
        pool_name = self.get_config('pool_name') or 'smart_data'
        # looking for the right pool
        pools = self.rados.list_pools()
        is_pool = False
        for pool in pools:
            self.log.debug('pool name is %s' % pool)
            if pool == pool_name:
                is_pool = True
                break
        if not is_pool:
            self.rados.create_pool(pool_name)
            self.log.debug('create %s pool' % pool_name)
        ioctx = self.rados.open_ioctx(pool_name)
        return (ioctx)

    def handle_osd_smart_scrape(self, osd_id):
        ioctx = self.open_connection()
        self.do_osd_smart_scrape(osd_id, ioctx)
        ioctx.close()
        return (0, "", "")

    def do_osd_smart_scrape(self, osd_id, ioctx):
        # running 'tell' command on OSD, retrieving smartctl results
        result = CommandResult('')
        self.send_command(result, 'osd', osd_id, json.dumps({
            'prefix': 'smart',
            'format': 'json',
        }), '')
        r, outb, outs = result.wait()
        # TODO add try-catch block for json
        smart_data = json.loads(outb)

        osd_host = self.get_metadata('osd', osd_id)['hostname']
        if not osd_host:
            self.log.debug('cannot get osd hostname of osd_id: %s' % osd_id)
            return
        self.log.debug('osd hostname %s' % osd_host)

        for device, device_smart_data in smart_data.items():
            object_name = osd_host + ":" + device
            with rados.WriteOpCtx() as op:
                # TODO should we change second arg to be byte?
                # TODO what about the flag in ioctx.operate_write_op()?
                now = time.strftime(TIME_FORMAT)
                ioctx.set_omap(op, (now,), (str(json.dumps(device_smart_data)),))
                ioctx.operate_write_op(op, object_name)
                self.log.debug('writing object %s, key: %s, value: %s' % (object_name, now, str(json.dumps(device_smart_data))))

    def handle_osd_smart_scrape_all(self):
        osdmap = self.get("osd_map")
        assert osdmap is not None
        ioctx = self.open_connection()
        for osd in osdmap['osds']:
            osd_id = osd['osd']
            self.log.debug('scraping osd %s for smart data' % str(osd_id))
            self.do_osd_smart_scrape(str(osd_id), ioctx)
        ioctx.close()
        return (0, "", "")

    # TODO add changes here - avoid duplication
    def predict_failure(self, model, action):
        ioctx = self.open_connection()
        object_iterator = ioctx.list_objects()
        while True:
            try:
                rados_object = object_iterator.next()
                obj_name = rados_object.key
                self.log.debug('object name = %s' % rados_object.key)
                self.do_osd_smart_dump(obj_name, ioctx)
            except StopIteration:
                self.log.debug('iteration stopped')
                break
        ioctx.close()
        return

    def shutdown(self):
        self.log.info('Stopping')
        self.run = False
        self.event.set()

    # TODO maybe change 'begin' to be datetime object instead of str
    def seconds_to_next_run(self, begin, interval):
        now = datetime.now()
        # creating datetime object for today's first run
        today = date.today()
        begin_time = time(int(begin[0:2]), int(begin[2:4]))
        begin_time_today = datetime.combine(today, begin_time)
        # In case we missed today's first run - rewinding the clock a day,
        # and calculating the next run by adding the seconds interval.
        # This assumes a minimum of one daily run.
        if begin_time_today > now:
            begin_time_today -= timedelta(days=1)
        while begin_time_today < now:
            begin_time_today += timedelta(seconds=interval)
        delta = begin_time_today - now
        return int(delta.total_seconds())

    def serve(self):
        self.log.info("Starting")
        while self.run:
            # TODO see if there might be a bug if active == false
            self.active = self.get_config('active', '') is not ''
            # TODO convert begin string to a datetime object
            begin_time = self.get_config('begin_time') or '0000'
            scrape_frequency = self.get_config('scrape_frequency') or SCRAPE_FREQUENCY
            failure_prediction_model = self.get_config('failure_prediction_model ') or 'trivial'
            failure_prediction_action = self.get_config('failure_prediction_action ') or 'warn'
            timeofday = time.strftime('%H%M%S', time.localtime())

            sleep_interval = seconds_to_next_run(begin_time, scrape_frequency)
            self.log.debug('Sleeping for %d', sleep_interval)
            ret = self.event.wait(sleep_interval)
            self.event.clear()

            # in case 'wait' was interrupted, it could mean config was changed
            # by the user; go back and read config vars
            if ret:
                continue
            # in case we waited the entire interval
            else:
                # TODO specify the exact time of next run
                self.log.debug('Waking up [%s, scheduled for %s, now %s]',
                               "active" if self.active else "inactive",
                               begin_time, timeofday)
                if self.active:
                    self.log.debug('Running')
                    self.handle_osd_smart_scrape_all()
                    self.predict_failure(failure_prediction_model, failure_prediction_action)

    # TODO remove
    def get_smart_attr_val(self, table, t_id):
        for item in table:
            self.log.debug('desired table id is %s and curr val is: %s' % (t_id, item['id']))
            self.log.debug('item type is: %s' % type(item))
            self.log.debug('table type is: %s' % type(table))
            if item['id'] == t_id:
                return item
        return None

    # TODO remove
    def get_lastest_scrape_date(self, ioctx, obj_name):
        with rados.ReadOpCtx() as read_op:
            iter, ret = ioctx.get_omap_keys(read_op, "", -1)
            assert(ret == 0)
            ioctx.operate_read_op(read_op, obj_name)
            latest = 0
            for date, none in list(iter):
                date = str(date)
                if date > latest:
                    latest = date
        return latest

    # TODO remove
    def get_scrape_of_date(self, ioctx, obj_name, date):
        scrape_dump = 0
        with rados.ReadOpCtx() as read_op:
            iter, ret = ioctx.get_omap_vals_by_keys(read_op, (date,))
            assert(ret == 0)
            ioctx.operate_read_op(read_op, obj_name)
            for (k, v) in list(iter):
                # self.log.debug("date requested is: %s and value is: %s" % (k, v))
                scrape_dump = v
        return scrape_dump

    # TODO maybe add a 'date' param, for 'start key' in get_omap_vals
    def do_osd_smart_dump(self, obj_name, ioctx):
        """
        date = self.get_lastest_scrape_date(ioctx, obj_name)
        self.log.debug("hello___: %s" % date)
        # TODO check that date exist
        scrape_dump = self.get_scrape_of_date(ioctx, obj_name, date)
        self.log.debug("hello wow val is: %s" % scrape_dump)
        """
        smart_dump = {}
        with rados.ReadOpCtx() as op:
            # TODO ask from a specific key (specific date)
            iter, ret = ioctx.get_omap_vals(op, "", "", -1)
            assert(ret == 0)
            ioctx.operate_read_op(op, obj_name)
            # k == date; v == json_blob
            for (k, v) in list(iter):
                self.log.debug('Dumping SMART data of object: %s, key: %s, val %s' % (obj_name, k, v))
                try:
                    smart_dump[k] = json.loads(str(v))
                    # TODO move this
                    """
                    table = json.loads(str(v))
                    self.log.debug('ata version is: %s' % table['ata_version'])
                    self.log.debug('ata_smart_attributes are: %s' % table['ata_smart_attributes']['table'][0]['id'])
                    self.log.debug('calling table func: ')
                    res = self.get_smart_attr_val(table['ata_smart_attributes']['table'], 5)
                    self.log.debug("result from table read is: %s" % res)
                    self.log.debug("value is read is: %s" % res['value'])
                    res = self.get_smart_attr_val(table['ata_smart_attributes']['table'], 187)
                    self.log.debug("value of read is: %s --------" % res['value'])
                    """
                except:
                    # TODO get the full error message
                    self.log.debug('Probably invalid or empty JSON')
        return str(json.dumps(smart_dump))

    def handle_osd_smart_dump(self, cmd):
        ioctx = self.open_connection()
        smart_dump = self.do_osd_smart_dump(cmd['obj_name'], ioctx)
        ioctx.close()
        return (0, "", str(smart_dump))

    def handle_osd_smart_dump_all(self):
        ioctx = self.open_connection()
        object_iterator = ioctx.list_objects()
        # TODO see whether to change return val
        smart_dump = {}
        while True:
            try:
                rados_object = object_iterator.next()
                obj_name = rados_object.key
                self.log.debug('object name = %s' % rados_object.key)
                smart_dump[obj_name] = self.do_osd_smart_dump(obj_name, ioctx)
            except StopIteration:
                self.log.debug('iteration stopped')
                break
        ioctx.close()
        # TODO maybe have a wrapper for the cmd call
        # and return 0 or 1 here (and json obj)
        return (0, "", str(smart_dump))

    def handle_command(self, cmd):
        self.log.info("Handling command: '%s'" % str(cmd))

        if cmd['prefix'] == 'smart status':
            s = {
                'active': self.active,
            }
            return (0, json.dumps(s, indent=4), '')

        elif cmd['prefix'] == 'smart on':
            if not self.active:
                self.set_config('active', '1')
                self.active = True
            self.event.set()
            return (0, '', '')

        elif cmd['prefix'] == 'smart off':
            if self.active:
                self.set_config('active', '')
                self.active = False
            self.event.set()
            return (0, '', '')

        elif cmd['prefix'] == "osd smart scrape":
            return self.handle_osd_smart_scrape(cmd['osd_id'])

        elif cmd['prefix'] == "osd smart scrape-all":
            return self.handle_osd_smart_scrape_all()

        elif cmd['prefix'] == "osd smart dump":
            return self.handle_osd_smart_dump(cmd)

        elif cmd['prefix'] == "osd smart dump-all":
            return self.handle_osd_smart_dump_all()

        elif cmd['prefix'] == "smart warn":
            # TODO check why it's not in 'ceph health' output
            self.set_health_checks({
                'MGR_TEST_WARNING': {
                    'severity': 'warning',
                    'summary': 'test warning',
                    'detail': ['details about the warning']
                }
            })
            return (0, "warn", "test")

        else:
            # mgr should respect our self.COMMANDS and not call us for
            # any prefix we don't advertise
            raise NotImplementedError(cmd['prefix'])
