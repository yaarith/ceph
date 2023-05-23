import json

from threading import Event
from typing import cast, Any, DefaultDict, Dict, List, Optional, Tuple, TypeVar, TYPE_CHECKING, Union

from mgr_module import CLIReadCommand, HandleCommandResult, MgrModule, Option

class Collect(MgrModule):

    def get_inventory(self) -> Dict[Any, Any]:
        report = {}
        report["crush_map"] = self.get("osd_map_crush")
        report["devices"] = self.get("devices")
        report["df"] = self.get("df")
        report["fs_map"] = self.get("fs_map")
        report["hosts"] = self.list_servers()
        report["manager_map"] = self.get("mgr_map")
        report["mon_map"] = self.get("mon_map")
        report["osd_map"] = self.get("osd_map")
        report["osd_metadata"] = self.get("osd_metadata")
        report["osd_tree"] = self.get("osd_map_tree")
        report["pg_summary"] = self.get("pg_summary")
        report["service_map"] = self.get("service_map")

        return report

    @CLIReadCommand('collect inventory')
    def cli_inventory(self) -> HandleCommandResult:
        return HandleCommandResult(stdout=f'{self.get_inventory()}')
