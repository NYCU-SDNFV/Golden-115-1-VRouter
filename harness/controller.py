#!/usr/bin/env python3
"""Editable os-ken controller for the FRR-backed OVS routed data plane.

The controller consumes real kernel FIB and neighbor JSON from each FRR
namespace.  os-ken is used only as the OpenFlow codec/lifecycle library; the
route selection and forwarding decisions remain visible in routing.py.

Runtime contract.  The protected harness/runtime.py and harness/checks.py rely
on the points below; the record types are in harness/contracts.py.

* `make deploy PLANE=ovs` starts this app with osken-manager, exports
  LAB3_STATE_DIR (STATE_DIR below) and then points every bridge at
  tcp:127.0.0.1:6653.  Bridge br-l3-N has datapath id N (AS N).
* Health file.  Keep STATE_DIR/controller.json (a ControllerState) current and
  write it atomically (see _atomic_json):
    - "ready": true once the initial FIB import is installed;
    - "datapaths": the connected datapath ids, which must be [1, 2, 3, 4];
    - "updated": time.time() of the latest refresh.  Rewrite the file at least
      every 3 seconds; an older file marks the deployment unhealthy;
    - "last_error": "" while healthy; any other text aborts the deployment;
    - "routes": {"1": [...], ..., "4": [...]}, the routes imported for each AS
      as RouteRecord objects.  Deployment waits up to 25 seconds for AS1 to
      list 10.3.0.0/24 and 2001:db8:3::/64;
    - "neighbor_resolution": optional per-next-hop diagnostics.
* Route flows.  Install exactly one flow per (family, prefix), at priority
  flow_priority(prefix), with a cookie whose upper 32 bits are 0x4c330000
  (the lower 32 bits are yours).  The checks compare these flows with the real
  FIB and neighbor tables.  Any IPv4/IPv6 flow at priority 1000 or above
  without that cookie is reported as an unowned route flow.
* The topology pre-installs cookie-0 control flows (priorities 4100 and 4200)
  that carry BGP, ARP and ND between each speaker and its peer.  If you delete
  them, your controller must deliver that control traffic itself.
* A hop limit that expires in OVS reaches the controller as a PacketIn with
  reason OFPR_INVALID_TTL (see dec_ttl in ovs-actions(7)).  Deployment traces
  that path for IPv4 and IPv6 and fails if it does not reach the controller.
* Check B10 stops this process with SIGSTOP.  The flows you installed must keep
  forwarding existing traffic with no further help from the controller.
"""
from __future__ import annotations

import json
import ipaddress
import logging
import os
import subprocess
import time
import zlib
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, cast

from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from os_ken.lib import hub
from os_ken.ofproto import ofproto_v1_3

from harness.contracts import (
    CommandOutput, ControllerState, InterfaceMap, NeighborDiagnostic, Neighbors,
    RouteKey,
)
from harness.openflow import Datapath13, Parser13
from harness.routing import (
    Route, RouteTable, build_arp_reply, build_icmpv4_time_exceeded,
    build_icmpv6_time_exceeded, build_nd_advertisement, flow_priority,
    forwarding_actions, parse_fib, parse_neighbors, resolve_next_hop,
)
from topo.model import ASState, TopologyState, port_number

if TYPE_CHECKING:
    from os_ken.ofproto.ofproto_v1_3_parser import OFPAction, OFPMatch

LOG = logging.getLogger("lab3.controller")
STATE_DIR = Path(os.environ.get("LAB3_STATE_DIR", "/run/lab3"))


def _run(namespace: str, argv: Sequence[str], timeout: float = 5) -> str:
    command = ["ip", "netns", "exec", namespace] + list(argv)
    proc = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=timeout, check=False)
    if proc.returncode:
        raise RuntimeError("%s failed (%d): %s" %
                           (" ".join(command), proc.returncode, proc.stderr.strip()))
    return proc.stdout


def _atomic_json(path: Path, value: object) -> None:
    pending = path.with_suffix(path.suffix + ".new")
    with pending.open("w", encoding="ascii", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(str(pending), str(path))


class VirtualRouter(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        raise NotImplementedError("TODO controller: import the FRR FIB, maintain LPM flows, handle gateways, and emit ICMP Time Exceeded")
