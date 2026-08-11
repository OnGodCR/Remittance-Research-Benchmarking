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
    Realism technique #1, the same four corridors as phases 2 and 3.

    Keeping them identical is what makes the three-way comparison fair: every
    architecture pays the same geographic latency. Changing regions between
    architectures would put a real confound inside the headline result.

      us-east4        Virginia  -- US, largest sending country
      asia-south1     Mumbai    -- India, largest receiving country
      asia-southeast1 Singapore -- SE Asia / Philippines corridor
      europe-west2    London    -- UK, major sender to South Asia

    Two validators per region gives the 8 the quota allows.
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

variable "validators_per_region" {
  description = <<-EOT
    2 per region, 8 total. This number is set by QUOTA, not by preference.

    claude.md S4 sizes the cluster at 8-12 validators, enough to populate at
    least 4 shards with at least 2 validators each. 12 validators plus a
    generator needs 104 vCPU; the project ceiling is 96, a request for 144 was
    denied on 10 Aug and 120 is pending. 8 validators plus the generator is 72
    and fits.

    Eight satisfies the sizing rule exactly and leaves NO margin: with 4 shards
    that is 2 validators per shard, so losing one node drops a shard to a
    single validator. NEAR's adversarial arm is therefore harsher than
    Polygon's was, where losing one of four still left three. State that when
    the two are compared -- it is a constraint, not a design choice.
  EOT
  type    = number
  default = 2
}

variable "num_shards" {
  description = <<-EOT
    Pinned to 4, and this must match `expected_shards` in the NEAR adapter.

    If the chain comes up with a different number, either some shard has fewer
    than 2 validators, or every transfer becomes same-shard and the arm
    measures a chain that is not actually dividing work. The adapter's health
    check refuses to run below this, so a mismatch fails loudly rather than
    producing a plausible wrong number.
  EOT
  type    = number
  default = 4
}

variable "machine_type" {
  description = <<-EOT
    Realism technique #4, matched to NEAR's published validator specification.

    NEAR documents 8 vCPU / 16 GB minimum for a validator, with 32 GB
    recommended for mainnet chunk producers. n2-standard-8 gives 8 vCPU / 32 GB
    -- the same instance used for Polygon's validators, which keeps the
    hardware variable constant across the comparison.
  EOT
  type    = string
  default = "n2-standard-8"
}

variable "generator_machine_type" {
  description = <<-EOT
    Identical to phases 2 and 3. The harness core is unchanged, so its capacity
    ceiling must be unchanged too -- a different generator would mean the three
    architectures were measured with differently-capable instruments.
  EOT
  type    = string
  default = "n2-standard-8"
}

variable "disk_size_gb" {
  description = <<-EOT
    claude.md S5 #4: match CPU and RAM, do NOT match storage.

    NEAR publishes ~1 TB for a mainnet validator, but that figure exists to
    hold years of chain history. Ours starts empty and accumulates a few hours
    of blocks. Provisioning 1 TB across 9 nodes would burn hundreds of dollars
    storing nothing, and storage is not what determines consensus or execution
    performance.
  EOT
  type    = number
  default = 100
}

variable "use_spot" {
  description = <<-EOT
    Spot for validators, on demand for the generator -- the split learned in
    phase 3.

    A reclaimed validator costs a rebuild of one node. A reclaimed GENERATOR
    stops all data collection and nothing restarts it, because a preempted spot
    instance stays STOPPED. That happened mid-deployment on 10 Aug. One
    n2-standard-8 on demand is about $0.27/hr more, against a sweep that would
    otherwise stall silently overnight.
  EOT
  type    = bool
  default = true
}

variable "idle_shutdown_minutes" {
  description = <<-EOT
    Shut down after this long with no measured activity.

    NOTE the phase 3 trap: the idle watcher's activity signal must match the
    architecture. Phase 1's watcher polls an Ethereum RPC, which does not exist
    on a Lightning host, so it read zero forever and killed that cluster five
    times. For NEAR the honest signal is chunk production or transaction count,
    NOT eth_blockNumber.
  EOT
  type    = number
  default = 45
}

variable "max_lifetime_minutes" {
  description = <<-EOT
    Hard cap, armed at boot. Phase 3 lesson: size this to cover the WHOLE
    sweep. The caps there were set for a short deployment and would have killed
    the generator three hours into a twenty-hour run.
  EOT
  type    = number
  default = 2040
}

variable "near_version" {
  description = <<-EOT
    nearcore release, pinned. claude.md S3 requires live, maintained,
    production node software at a fixed commit -- pinning aids reproducibility
    rather than harming it.
  EOT
  type    = string
  default = "2.3.1"
}
