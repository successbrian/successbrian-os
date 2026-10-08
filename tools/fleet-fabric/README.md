# Fleet Fabric — NVMe-over-Fabrics for the Brian fleet

## PURPOSE
Share NVMe and SSD block storage across the fleet over the existing 1GbE / 2.5GbE
network, so Colibri inference workers on machines without local NVMe (DL380 Gen8s)
can stream model weights from machines that have it (X79s, k11 nodes, Aoostars).

## WHY
- Gen8s have no NVMe slots. Their Colibri NVMe tier would otherwise be local SATA SSDs.
- The fabric lets any node export any block device (NVMe, SATA SSD) and any node
  consume it as a local NVMe device via NVMe/TCP (`nvmet` target + `nvme-tcp` initiator).
- Peer-to-peer: every node is a potential exporter. No single designated array host.
- Fleet survives any exporter host going down: models are replicated on all four X79s
  and initiators use nvme multipath for automatic path failover.
- Runs on the EXISTING network. No 10GbE required. DL380s bond 3x 1GbE (LACP,
  ~330MB/s aggregate); exporters use 2.5GbE where available.

## ARCHITECTURE (decided 2026-10-08)
- Exporters: 4x X79 (Mantis-1..4, each +2.5GbE NIC), k11-alpha (2.5GbE), k11-bravo
  (2.5GbE), 2x Aoostar 24GB (2.5GbE, NVMe). DL380s can export SATA SSDs in a pinch.
- Consumers: 2x DL380 Gen8 (Proxmox hosts). The PROXMOX HOST connects the fabric
  once; VM slices get virtual disks backed by fabric namespaces.
- Model placement: 150B DeepSeek weights live in MULTIPLE places (X79 NVMe replicas,
  k11-alpha source, local copies where useful). The fabric distributes; it is not the
  sole source of truth.
- Sharing model: namespaces are exported for shared READ. Multiple initiators may
  connect to the same namespace read-only. KV cache and scratch are ALWAYS local
  per-slice writable volumes, never shared.
- Read-only enforcement is initiator-side (`mount -o ro` / read-only attach) plus
  checksum verification on sync. All initiators are fleet-owned boxes.

## LAYOUT
- `fleet-fabric.conf.example` — copy to `fleet-fabric.conf`, fill in your IPs/devices.
- `target/nvmet-export.sh` — run on each exporter. Idempotent; safe to re-run.
- `target/nvmet-fabric.service` — systemd unit; export comes back after reboot.
- `initiator/nvme-fabric-connect.sh` — run on each consumer (Proxmox host).
  Enables nvme multipath, discovers and connects all targets in the conf.
- `initiator/nvme-fabric.service` — systemd unit; reconnects after reboot.
- `network/proxmox-bond-fabric.cfg` — LACP bond snippet for /etc/network/interfaces.d/
  on the DL380 Proxmox hosts (3x 1GbE -> bond0 on the fabric VLAN/subnet).
- `sync/model-sync.sh` — rsync model weights from source to replicas + sha256 verify.
- `health/fabric-health.sh` — verify targets reachable, namespaces visible, multipath
  path counts healthy. Run manually or from cron.

## BRING-UP ORDER
1. Fill in `fleet-fabric.conf` on every node (copy the example).
2. Exporters: run `target/nvmet-export.sh`, enable the systemd unit.
3. Consumers: configure the bond (`network/proxmox-bond-fabric.cfg`), run
   `initiator/nvme-fabric-connect.sh`, enable the systemd unit.
4. Sync models: `sync/model-sync.sh` from the source host.
5. Verify: `health/fabric-health.sh` on a consumer. Expect every namespace visible
   with >=2 paths (multipath).
6. Hand the resulting block devices to Proxmox as VM disks (virtio-scsi), one
   read-only model disk per inference slice + one local writable disk per slice
   for KV/scratch.

## MAINTENANCE
To take an exporter down: nothing special. Initiators fail over to surviving paths
automatically. When it returns, re-run `sync/model-sync.sh` if weights changed,
then `target/nvmet-export.sh` (idempotent) to re-export.

## NOTES
- Kernel requirement: Linux 5.4+ on all nodes (nvmet-tcp). Proxmox VE 8 / Debian 12 fine.
- `nvme-cli` package required on initiators.
- Jumbo frames NOT assumed. Standard 1500 MTU; revisit only if measurements demand.
- Colibri NVMe-tier traffic per worker is UNMEASURED as of 2026-10-08. The k11-alpha
  resurrection test must measure it; if 1GbE links prove insufficient, the network
  gets upgraded then — not before.
