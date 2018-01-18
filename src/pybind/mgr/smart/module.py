
"""
Pulling SMART data from OSD
"""

import json
from mgr_module import MgrModule, CommandResult


class Module(MgrModule):
    COMMANDS = [
        {
            "cmd": "osd smart get "
                   "name=osd_id,type=CephString,req=true",
            "desc": "Get smart data for osd_id",
            "perm": "r"
        },
        {
            "cmd": "osd smart get all",
            "desc": "Get smart data for osd.id",
            "perm": "r"
        },
    ]

    def handle_osd_smart_get(self, osd_id):
        result = CommandResult('')
        self.send_command(result, 'osd', osd_id, json.dumps({
            'prefix': 'smart',
            'format': 'json',
        }), '')
        r, outb, outs = result.wait()

        return (r, outb, outs)

    def handle_command(self, cmd):
        self.log.error("handle_command")

        if cmd['prefix'] == "osd smart get":
            r, outb, outs = self.handle_osd_smart_get(cmd['osd_id'])

            return (r, outb, outs)

        elif cmd['prefix'] == "osd smart get all":
            osdmap = self.get("osd_map")
            assert osdmap is not None

            smart_map = {}
            # TODO what do we do in case of many osds? should we query all osds concurrently?
            for osd in osdmap['osds']:
                osd_id = osd['osd']
                r, outb, outs = self.handle_osd_smart_get(str(osd_id))
                smart_map[osd_id] = json.loads(outb)

            # TODO do we need to keep the other r and outs values?
            return (r, json.dumps(smart_map), outs)

        else:
            # mgr should respect our self.COMMANDS and not call us for
            # any prefix we don't advertise
            raise NotImplementedError(cmd['prefix'])
