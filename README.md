# Lab 3 - NFV: an SDN network as a virtual router

**SDNFV (CSIC30127), 115-1 - NYCU Institute of Network Engineering**

Build on Lab 1: forwarding decisions now come from BGP routes, not only learned
Ethernet addresses. There is no ONOS dependency. FRR supplies routing information;
your controller turns that information into OVS forwarding behavior.

**Grading:** the take-home autograder has 100 points, scaled to **40%** of this
lab. The supervised checkpoint is **35%** and viva **25%**, without personal AI.
Using AI for the take-home work is allowed; disclose it and verify its output.
Protected-file integrity failure gives **0/100 for the entire take-home part**.

## 1. What you are building

```text
Control:  FRR BGP -> selected routes/FIB -> your controller -> OVS flow rules
Data:     customer -> OVS virtual router -> next-hop virtual router -> customer

             AS1 -------- AS2 -------- AS3
               \_______________________/
                       alternate path
```

The supplied lab also exercises bringing another AS into service. Use
`make status` to inspect the actual addresses, peers, routes and process state.
Do not assume an IP diagram alone proves which path your packets took.

### Part A: establish a routed baseline

1. Configure real IPv4 and IPv6 eBGP sessions and customer-prefix announcements.
   An Established session without the required prefixes is not success.
2. Verify both address families across customer networks using FRR/Linux routing.
   Inspect the selected route and next hop, not just the ping exit code.
3. Put a VXLAN overlay over the routed IPv4 underlay. Capture UDP/4789, the VNI
   and the inner packet, and test the MTU boundary.

### Part B: make OVS do the routing

Import the actual routing information and maintain forwarding rules as routes
appear, change and disappear. The implementation must handle:

- **Intra-domain:** same-subnet Ethernet forwarding, without consuming an IP hop.
- **Inter-domain:** traffic between neighboring AS customer networks.
- **Transit:** an AS forwarding traffic between two other ASs.
- IPv4 and IPv6 in **all three** traffic classes; there is no two-class shortcut.
- Longest-prefix matching, next-hop resolution, and correct source/destination
  Ethernet rewrites.
- IPv4 TTL and IPv6 Hop Limit, including valid ICMP Time Exceeded exceptions.
- Gateway ARP/neighbor discovery and delivery of BGP control traffic.
- Withdrawal, alternate paths after a failed link, routing-policy changes and
  a newly activated AS.
- Existing installed data flows continuing to work when the controller stops.
  This does not promise that new neighbors, exceptions or route updates work
  without a controller.

The OVS mode must not secretly use Linux forwarding for ordinary transit
packets. Route tables, flow tables, counters, packet observations and the
control-down test are complementary evidence. Whether `mtr` displays a
particular FRR IP is **not** a sufficient correctness test.

## 2. Environment and first run

Use the course Linux VM with Docker and Docker Compose. Run all host commands
from the repository root. Windows users should use the course VM or WSL2, not
Git Bash (which rewrites Docker paths). Full Lab 3 validation is performed on
the course Linux/PVE environment; macOS and other Docker kernels are not
implicitly certified.

Run the non-scoring `make pretest` before starting. If it reports a
host prerequisite, follow the [course environment preparation guide](.github/golden/README.md)
on the machine that actually runs the Docker Engine. The pretest uses isolated
privileged probes and does not change host sysctl policy or your answers.
Probes can trigger normal Linux module autoload; use an authorized dedicated lab
VM, not a shared production Docker host.

The supplied image is pinned to an immutable course image in `Dockerfile`. It contains FRR, OVS,
namespace tools, `tcpdump`, `ethtool`, `ping` and `iperf3`. Do not install another
controller framework or change protected infrastructure to make a test pass.
The container is privileged because it creates isolated networking resources;
only use it on an authorized lab machine.

```sh
make pretest
make up
sh tests/00_env.sh
make deploy PLANE=frr
make a
make deploy PLANE=ovs
make b
make status
```

An unfinished exercise should fail with a named error. Read that error and the
retained logs. `make up` starts the supplied environment; it does not solve the
student implementation or prove BGP/forwarding correctness.

Inside `make shell`, the runtime interface is:

```sh
python3 harness/lab3.py status --json
python3 harness/lab3.py check transit4 --json
python3 harness/lab3.py check transit6 --json
```

Read the exercise docstrings in [harness/routing.py](harness/routing.py) and
[harness/controller.py](harness/controller.py). The module docstring of
`controller.py` lists the runtime contract your controller must meet: the
health file the deployment waits for, the cookie and priority of route flows,
and the control flows the topology pre-installs. os-ken supplies the OpenFlow
codec; the routing and controller behavior are your implementation. Only change the marked student implementation and
your report/disclosure. A file in the integrity manifest is given infrastructure,
not an exercise. The official grader runs a fresh canonical copy of the checks.

### Reading types in the student code

The generated starter retains parameter/return annotations on the exercises,
including the separate unfinished controller constructor. Editor hover exposes
`Route | None`, `(changed, withdrawn)` route lists, the forwarding-plan fields,
and kernel/topology records. Missing packet replies are `bytes | None`, not an
empty successful packet. Ports in an in-progress topology may not have an
`ofport` yet; [topo/model.py](topo/model.py) describes that distinction.

[pyrightconfig.json](pyrightconfig.json) targets the course's Python 3.12/Linux
runtime. The [inspected os-ken subset](typings/README.md) supplies editor types
for OpenFlow 1.3 without installing Mininet or another controller framework.
These are declarations, not executable replacements for os-ken. A local editor
without os-ken may report that its runtime source is missing; use the course
container for execution. Type correctness does not complete a TODO or establish
BGP/forwarding correctness.

## 3. Experiments and evidence

Checks execute fresh probes rather than trusting a success JSON committed by a
student. Graded probe records are saved as `results/<plane>-<case>.json`; raw
runtime logs and packet captures remain available for debugging and your report.
The results must be from your own run.

In [REPORT.md](REPORT.md), document addressing, control/data separation, LPM and
route changes, Ethernet rewrites, hop behavior, failures, VXLAN, and limitations.
Include actual route/flow examples and numerical observations. Use:

```sh
python3 tests/grade.py evidence
```

to print the evidence block for the report: one `passed` claim for each listed
experiment, taken from your latest local runs (a missing or failed run is listed
as `false`). The TA compares these claims with your official results and your
demo. Absolute latency/throughput values are not used as machine-specific pass
thresholds. The TA assesses whether your explanations and interpretation of the
data are correct.

What `make report` (check R, 5 points) looks at -- these rules are the whole check:

- `REPORT.md` keeps all seven `##` section headings, and each section has at least
  80 characters of your own text. Lines starting with `TODO:` are the template's
  instructions and are not counted (delete them when you are done); headings and
  HTML comments are not counted either. Ordinary words such as "todo" or
  "placeholder" inside your sentences are fine.
- `REPORT.md` keeps exactly one `<!-- BEGIN EVIDENCE -->` ... `<!-- END EVIDENCE -->`
  block in the format printed by `python3 tests/grade.py evidence`: every listed
  experiment, its plane, and a `true`/`false` claim. Only the format is checked,
  not whether the experiments passed in the grading run, so a failed experiment
  costs its own points but never this check's. Only this block is parsed; your
  own tables and text elsewhere cannot break the check.
- `ai-usage.md` keeps its `## My verification` section with at least 80 characters of
  your own text (same counting rule). AI coding assistants that read `AGENTS.md`,
  `CLAUDE.md` or `.github/copilot-instructions.md` append rows to the `## Assistant log`
  table at the end of the file; that table is not counted. Add rows yourself for tools
  that cannot see this repository, such as a browser chat. Using no AI is valid: say so
  and describe how you verified your work.
- A failed check lists every problem it found at once.

The configured VXLAN example has an **IPv4 outer header**: a 1500-byte underlay
leaves 1450 bytes for the overlay IP MTU. Do not generalize the 50-byte overhead
to an IPv6 outer header, extra VLAN tags or additional tunnels.

## 4. The 100-point take-home rubric

| Item | Command | Points |
|---|---|---:|
| Repository layout | `make policy` | 5 |
| Protected-file integrity | `make policy` | 5 |
| Container startup | `make up` | 5 |
| FRR/OVS environment | `sh tests/00_env.sh` | 0 |
| A1: IPv4 + IPv6 eBGP | `make a1` | 10 |
| A2: FRR/Linux dual-stack baseline | `make a2` | 5 |
| A3: VXLAN + MTU | `make a3` | 5 |
| B0: OVS vrouter deployment | `make b0` | 5 |
| B1: intra-domain v4/v6 | `make b1` | 5 |
| B2: inter-domain v4/v6 | `make b2` | 5 |
| B3: transit v4/v6 + routed VXLAN | `make b3` | 10 |
| B4: FIB/flow consistency | `make b4` | 5 |
| B5: TTL/Hop Limit and ICMP exceptions | `make b5` | 5 |
| B6: withdrawal + restoration | `make b6` | 5 |
| B7: failed link + alternate path | `make b7` | 5 |
| B8: routing-policy change | `make b8` | 5 |
| B9: new AS | `make b9` | 5 |
| B10: control/data independence | `make b10` | 5 |
| Report and AI disclosure | `make report` | 5 |
| Git hygiene (at least three work commits) | `make git` | 0 |

`make test` checks release compatibility and then runs the full sequence.
`make test-offline` runs the same local checks without an online release lookup;
it is useful for an unpublished instructor build or an offline course VM.
Official grading still uses the registered canonical release and manifest.
Zero-point checks remain checks; do not remove them.

## 5. Submission, updates and cleanup

Use the assignment invitation supplied by the TA and work in your assigned
private repository. Submit implementation, [REPORT.md](REPORT.md) and
[ai-usage.md](ai-usage.md). Push to your Classroom repository; every push is
autograded and the result appears as a Release on your repository. Use the
deadline announced by your instructor; this guide does not set one. Upload
`REPORT.md` as a PDF to E3 as well: the repository copy is for the autograder,
the E3 copy is what the TA reads and grades.

`results/` and `captures/` are not committed (see `.gitignore`); they are
regenerated by every run. Commit as you work. Do not commit secrets, generated
caches or instructor materials.

After a released starter update, use `make check-update` and the instructor
update PR or `make update`. Do not rewrite protected hashes yourself.

```sh
make clean
```

removes this lab's topology and container but retains evidence. Deployment and
cleanup must be safe to repeat. Never use a broad `pkill`, stop another student's
container, or change the PVE hypervisor network to repair your lab.

## 6. Supervised checkpoint and viva

You work at a course seat with **your** repository at its state at the
deadline, no Internet and no personal AI. Use `make test-offline` there, never
`make test` (its online release check cannot reach GitHub). Because `results/`
and `captures/` are not committed, any evidence you want to show is produced
again on the seat by rerunning the relevant `make` target.

**Checkpoint (35).** The TA injects a failed link, activates an AS, or changes a
routing policy. Predict the result for IPv4 and IPv6 before changing anything,
demonstrate the observed behavior and explain the route/flow changes and
convergence. Marks: prediction 15, demonstration 10, explanation 10.

**Viva (25).** The questions are about your own code and your own evidence on
the seat: how your rules treat an actual packet and an actual route change. The
private question bank is not part of the student template.

Be fluent with these inside `make shell` (`N` is the AS number; ignore vtysh's
missing `vtysh.conf` warning):

| What you look at | Commands |
|---|---|
| FRR's BGP view | `ip netns exec l3-rN vtysh -N lab3-rN -c 'show bgp summary'`, `-c 'show bgp ipv4 unicast'`, `-c 'show bgp ipv6 unicast'` |
| the kernel FIB and neighbors your controller imports | `ip netns exec l3-rN ip -j route` (add `-6` for IPv6), `ip netns exec l3-rN ip neigh` |
| the rules you installed | `ovs-ofctl -O OpenFlow13 dump-flows br-l3-N` (watch `n_packets`) |
| a packet on a wire | `tcpdump -nn -e -i <OVS port>`, or `ip netns exec <namespace> tcpdump -nn -e` |
| a host's view | `ip netns exec l3-h1a ping ...`, `ip netns exec l3-h1a ip neigh` |
| the whole runtime | `python3 harness/lab3.py status --json` |

How to prepare: for every rule your controller installs, be able to say which
route and which neighbor entry it came from, what each action does to the
packet, and what happens to it when the route is withdrawn or replaced, or when
the controller stops. If you can do that from your own `dump-flows` output, you
have prepared for the whole session. If you cannot answer a question about your
own code or report, that question scores 0 and the take-home part is
re-examined.

Anycast, additional tunnels and a cross-group topology are extensions, not
substitutes for the required three traffic classes.

## Sources

- [FRRouting 8.4 BGP documentation](https://docs.frrouting.org/en/stable-8.4/bgp.html)
- [FRRouting Zebra and the forwarding plane](https://docs.frrouting.org/en/stable-8.4/zebra.html)
- [Open vSwitch actions: routing, Ethernet rewrites and TTL](https://www.openvswitch.org/support/dist-docs/ovs-actions.7.html)
- [RFC 1812: IPv4 router requirements](https://www.rfc-editor.org/rfc/rfc1812)
- [RFC 8200: IPv6 and Hop Limit](https://www.rfc-editor.org/rfc/rfc8200)
- [RFC 4443: ICMPv6](https://www.rfc-editor.org/rfc/rfc4443)
- [RFC 4861: IPv6 Neighbor Discovery](https://www.rfc-editor.org/rfc/rfc4861)
- [RFC 7348: VXLAN](https://www.rfc-editor.org/rfc/rfc7348)
