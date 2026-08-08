variable "project_id" {
  description = "GCP project ID. Find it on the Cloud console home page."
  type        = string
}

variable "region" {
  description = <<-EOT
    Phase 1 runs in one region only. us-east4 is the US corridor node in the
    four-region plan, so Phase 1 hardware matches what Phase 2 expands into.
  EOT
  type        = string
  default     = "us-east4"
}

variable "zone" {
  type    = string
  default = "us-east4-c"
}

variable "validator_count" {
  description = <<-EOT
    Phase 1 uses 4, the smallest set that is still a genuine Byzantine
    fault-tolerant cluster (tolerates one faulty node). Phase 2 onward uses 7,
    which tolerates two and is the number the measured results are based on.

    Four is enough to prove the pipeline works, and consensus messaging grows
    with the square of node count, so 4 is meaningfully cheaper than 7.
  EOT
  type        = number
  default     = 4
}

variable "machine_type" {
  description = <<-EOT
    Matches real Polygon validator guidance on processor and memory
    (8 vCPU / 32 GB). Deliberately NOT matched on storage: published specs
    quote ~1.2 TB purely to hold years of mainnet history, which a fresh
    private chain does not have. See claude.md S5 technique #4.

    Keeping Phase 1 on the real spec means the cost baseline it produces is
    actually representative of later phases.
  EOT
  type        = string
  default     = "n2-standard-8"
}

variable "generator_machine_type" {
  description = <<-EOT
    Runs the measurement program. Verified on 7 Aug 2026 to sustain 300
    payments/second at ~1ms scheduling lag on a 8-core laptop, so this is
    ample. Kept separate from the validators so the load generator never
    competes with consensus for CPU.
  EOT
  type        = string
  default     = "n2-standard-4"
}

variable "disk_size_gb" {
  description = "100 GB. A fresh chain accumulates hours of blocks, not years."
  type        = number
  default     = 100
}

variable "use_spot" {
  description = <<-EOT
    Spot instances cost 60-90% less but Google can reclaim them at any time.

    The harness detects a reclaim mid-run and marks that run invalid rather
    than keeping it, because a reclaimed node looks exactly like the node
    failures the adversarial arm deliberately injects -- silently keeping such
    a run would confound the two.
  EOT
  type        = bool
  default     = true
}

variable "max_lifetime_minutes" {
  description = <<-EOT
    Hard shutdown timer, armed at boot on every machine.

    This is the project's most important cost control. Google's budget alerts
    only send email; they do not stop spending. The realistic way to waste
    real money here is not the measured runs, it is a cluster left running
    overnight during debugging. A 7-node cluster is roughly $1.15/hour, so a
    forgotten weekend is about $80.

    480 minutes covers the longest planned unattended sweep with headroom.
  EOT
  type        = number
  default     = 480
}

variable "idle_shutdown_minutes" {
  description = <<-EOT
    Shut down after this long with no benchmark activity.

    Detected by watching for connections to the node's RPC port, which only
    the measurement program talks to. Peer-to-peer consensus traffic uses a
    different port and continues regardless, so this cleanly distinguishes
    "cluster is idle" from "cluster is alive".
  EOT
  type        = number
  default     = 30
}

variable "operator_ip_cidr" {
  description = <<-EOT
    Your public IP, as a CIDR block, e.g. "203.0.113.4/32".
    Find it with: curl -s https://ifconfig.me

    Restricts SSH and RPC access to you alone. Leaving these ports open to the
    internet on a machine holding blockchain keys is how test clusters get
    conscripted into other people's botnets.
  EOT
  type        = string

  validation {
    condition     = can(cidrnetmask(var.operator_ip_cidr))
    error_message = "Must be valid CIDR notation, e.g. 203.0.113.4/32 (not a bare IP)."
  }
}

variable "edge_version" {
  description = <<-EOT
    The final Polygon Edge release. Verified 7 Aug 2026 against the GitHub
    releases API: v1.3.2, published 24 January 2024.

    The repository was archived read-only on 4 December 2024, so this is the
    last version that will ever exist. Pinning it is a reproducibility
    advantage rather than a compromise -- anyone repeating this study gets
    byte-identical software, which is not true of a maintained project.

    Do not change without re-verifying that the release and its Linux assets
    still exist.
  EOT
  type        = string
  default     = "v1.3.2"
}

variable "chain_id" {
  description = "Private chain identifier. Any value not used by a public network."
  type        = number
  default     = 100100
}

variable "labels" {
  description = "Applied to every resource so costs can be attributed in billing reports."
  type        = map(string)
  default = {
    project = "remittance-benchmarking"
    phase   = "phase-1"
    managed = "opentofu"
  }
}
