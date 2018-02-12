
"""
Pulling SMART data from OSD
"""

import json
from mgr_module import MgrModule, CommandResult
import rados
import time

OBJECT_NAME = "mytest"
ITER = 2
pool_name = "smart_data"

class Module(MgrModule):
    COMMANDS = [
        {
            "cmd": "osd smart scrape "
                   "name=osd_id,type=CephString,req=true",
            "desc": "Scraping SMART data of osd<osd_id>",
            "perm": "r"
        },
        {
            "cmd": "osd smart scrape all",
            "desc": "Scraping SMART data of all OSDs",
            "perm": "r"
        },
        {
            "cmd": "osd smart get "
                   "name=osd_id,type=CephString,req=true",
            "desc": "Get SMART data for osd_id",
            "perm": "r"
        },
        {
            "cmd": "osd smart get all",
            "desc": "Get SMART data for all OSDs",
            "perm": "r"
        },
        {
            "cmd": "pool test",
            "desc": "Just a pool test",
            "perm": "r"
        },
    ]

    def open_connection(self):
        # looking for the right pool
        # TODO open pool, and if it fails - create and open
        pools = self.rados.list_pools()
        is_pool = False
        for pool in pools:
            self.log.debug('pool name is %s' % pool)
            if pool == pool_name:
                is_pool = True
                break

        # TODO make pool name configurable
        if not is_pool:
            self.rados.create_pool(pool_name)
            self.log.debug('create %s pool' % pool_name)

        ioctx = self.rados.open_ioctx(pool_name)

        return (ioctx)

    def handle_osd_smart_scrape_all(self):
        osdmap = self.get("osd_map")
        assert osdmap is not None

        ioctx = self.open_connection()

        for osd in osdmap['osds']:
            osd_id = osd['osd']
            self.do_osd_smart_scrape(str(osd_id), ioctx)

        ioctx.close()
        return (0, "", "")

    def handle_osd_smart_scrape(self, osd_id):
        ioctx = self.open_connection()
        self.do_osd_smart_scrape(osd_id, ioctx);
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
        smart_data = json.load(bytes(outb))

        osd_host = self.get_metadata('osd', osd_id)['hostname']
        self.log.debug('osd host %s' % osd_host)

        for device, device_smart_data in smart_data.items():
            object_name = osd_host + ":" + device
            with rados.WriteOpCtx() as op:
                # TODO should we change second arg to be byte?
                # TODO what about the flag in ioctx.operate_write_op()?
                now = str(time.time())
                ioctx.set_omap(op, now, (str(json.dumps(device_smart_data)),))
                ioctx.operate_write_op(op, object_name)
                self.log.debug('writing object %s, key: %s, value: %s' % object_name, now, str(json.dumps(device_smart_data)))

        return (0, "do osd scrape", "test")

    def handle_command(self, cmd):
        self.log.error("handle_command")

        if cmd['prefix'] == "osd smart scrape":
            return self.handle_osd_smart_scrape(cmd['osd_id'])

        elif cmd['prefix'] == "osd smart scrape all":
            return self.handle_osd_smart_scrape_all()

        elif cmd['prefix'] == "osd smart get":
            return (0, "get", "test")

        elif cmd['prefix'] == "osd smart get all":
            return (0, "get all", "test")

        elif cmd['prefix'] == "pool test":
            return (0, "pool", "test")

        else:
            # mgr should respect our self.COMMANDS and not call us for
            # any prefix we don't advertise
            raise NotImplementedError(cmd['prefix'])
