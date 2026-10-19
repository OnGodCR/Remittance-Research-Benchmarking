variable "project_id" {
  type = string
}

variable "operator_ip_cidr" {
  description = "Your public IP as CIDR. Find it with: curl -s https://ifconfig.me"
  type        = string

  validation {
    condition     = can(cidrnetmask(var.operator_ip_cidr))
    error_message = "Must be CIDR notation, e.g. 203.0.113.4/32."
  }
}

variable "regions" {
  description = <<-EOT
    Realism technique #1, identical corridor mapping to phase 2.

    Keeping the same four regions is deliberate and not cosmetic: the
    cross-architecture comparison in phase 6 is only fair if every
    architecture paid the same geographic latency. Changing regions between
    architectures would put a real confound inside the headline comparison.

      us-east4        Virginia  -- US, largest sending country
      asia-south1     Mumbai    -- India, largest receiving country
      asia-southeast1 Singapore -- SE Asia / Philippines corridor
      europe-west2    London    -- UK, major sender to South Asia

    Each entry hosts one Lightning host running several LND nodes. Order fixes
    which region gets host 0..3 -- keep it stable so runs stay comparable, and
    so `harness/topology.py`'s host_index assignment stays meaningful.
  EOT
  type = list(object({
    region = string
    zone   = string
    role   = string
  }))
  default = [
    { region = "us-east4", zone = "us-east4-c", role = "US sender" },
    { region = "asia-south1", zone = "asia-south1-a", role = "India recipient" },
    { region = "asia-southeast1", zone = "asia-southeast1-a", role = "SE Asia recipient" },
    { region = "europe-west2", zone = "europe-west2-b", role = "UK sender" },
  ]
}

variable "generator_region_index" {
  description = <<-EOT
    Which region hosts the load generator. Index into `regions`, and it must
    match phase 2's choice for the same reason phase 2 fixed it: the
    generator's own network distance is part of every measurement.
  EOT
  type        = number
  default     = 0
}

variable "machine_type" {
  description = <<-EOT
    Realism technique #4, sized to published Lightning routing-node specs
    rather than to validator specs.

    A Lightning node is far lighter than a Polygon validator: it keeps channel
    state and a routing graph, not an executing EVM. Published guidance for a
    routing node is around 2 vCPU / 4-8 GB, and claude.md S5 #4 explicitly
    anticipates co-locating several per instance.

    e2-standard-4 (4 vCPU / 16 GB) holds five LND nodes plus, on host 0,
    bitcoind. The headroom is deliberate: a node starved of CPU would drop
    HTLCs and log a routing failure, which is exactly the measurement this arm
    produces. Under-provisioning here would not save money, it would fabricate
    the result.
  EOT
  type        = string
  default     = "e2-standard-4"
}

variable "generator_machine_type" {
  description = <<-EOT
    Same generator sizing as phase 2. The harness core is unchanged, so its
    capacity ceiling must be unchanged too -- a different generator would mean
    the two architectures were measured with differently-capable instruments.
  EOT
  type        = string
  default     = "n2-standard-8"
}

variable "disk_size_gb" {
  description = <<-EOT
    claude.md S5 #4: match CPU and RAM, do NOT match storage.

    A regtest chain mined by us holds hours of blocks, not years of history.
    50 GB is ample for bitcoind's regtest data plus 5 LND databases, and this
    is smaller than phase 2's 100 GB because there is no chain history at all
    to hold.
  EOT
  type        = number
  default     = 50
}

variable "use_spot" {
  description = <<-EOT
    Spot everywhere (RESUME_HERE.md S6). Preemption costs about 15 minutes of
    rebuild; on-demand costs 4.5x. The phase 2 lesson was an estimation error
    after switching to on-demand, not a problem with spot itself.

    Lightning has one extra preemption consequence worth knowing: losing a
    host loses its LND nodes' channel state, so the topology must be rebuilt
    before measuring resumes. `scripts/lightning_bootstrap.sh` is idempotent
    for exactly this reason.
  EOT
  type        = bool
  default     = true
}

variable "idle_shutdown_minutes" {
  description = "Shut down after this long with no measured payments. claude.md S8."
  type        = number
  default     = 30
}

variable "max_lifetime_minutes" {
  description = <<-EOT
    Hard cap, matching phase 2's 900 minutes. Note the phase 2 trap: this timer
    re-arms from each boot, not from creation, so a reboot silently extends the
    deadline (RESUME_HERE.md S5 trap 3).
  EOT
  type        = number
  default     = 900
}

variable "bitcoind_version" {
  description = "Bitcoin Core version. Pinned -- claude.md S4 requires production software at a fixed commit."
  type        = string
  default     = "27.1"
}

variable "lnd_version" {
  description = <<-EOT
    LND version, pinned.

    LND over Core Lightning or Eclair because LND dominates the real Lightning
    Network -- the same network Waugh & Holz measured -- so matching it is what
    makes the replication meaningful (claude.md S4).
  EOT
  type        = string
  default     = "v0.18.3-beta"
}

variable "nodes_per_host" {
  description = <<-EOT
    LND nodes co-located per instance. 20 nodes over 4 hosts.

    Must agree with `harness/topology.py`: MAJOR_HUBS + SECONDARY_HUBS +
    LEAF_NODES = 20, assigned to host_index 0..3. If these disagree the
    deployment will fund channels for nodes that do not exist.
  EOT
  type        = number
  default     = 5
}
