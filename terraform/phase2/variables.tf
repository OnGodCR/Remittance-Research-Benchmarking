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
    Realism technique #1: real geographic separation, so consensus pays real
    internet latency instead of datacentre latency.

    Regions are mapped to actual remittance corridors rather than picked for
    convenience. Same cost, and it means the deployment can be described in
    the paper as modelling real money flows rather than arbitrary geography:

      us-east4      Virginia   -- US, the largest sending country
      asia-south1   Mumbai     -- India, the largest receiving country
      asia-southeast1 Singapore -- SE Asia / Philippines corridor
      europe-west2  London     -- UK, a major sender to South Asia

    Virginia to Mumbai is roughly 200-250ms round trip. That is the baseline
    on which technique #2 later injects additional impairment.

    Each entry places one validator. The list order fixes which region gets
    validator 0, 1, 2, 3 -- keep it stable so runs stay comparable.
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
    Which region hosts the load generator. Index into `regions`.

    It must stay FIXED across every run and every phase. The generator's own
    network distance to the chain is part of every measurement, so moving it
    between runs would silently change the baseline and make results
    incomparable. Virginia (index 0) is chosen because it is the US sending
    side of the largest corridor.
  EOT
  type        = number
  default     = 0
}

variable "machine_type" {
  description = <<-EOT
    PHASE 2 STEP 1 uses the same small machines as Phase 1, deliberately.

    The phased rollout (claude.md S9) adds one realism technique at a time so
    that if results shift, the cause is unambiguous. This step changes ONLY
    geography. Hardware matching is technique #4 and comes two steps later --
    changing both at once would make it impossible to say which caused what.

    It also has to fit: the account's global processor cap is 32, and
    7 validators at 8 processors would need 60. Raise `CPUS_ALL_REGIONS`
    before attempting the hardware-matching step.
  EOT
  type        = string
  default     = "n2-standard-4"
}

variable "generator_machine_type" {
  type    = string
  default = "n2-standard-4"
}

variable "disk_size_gb" {
  description = "A fresh chain holds hours of blocks, not years of history."
  type        = number
  default     = 100
}

variable "use_spot" {
  type    = bool
  default = true
}

variable "max_lifetime_minutes" {
  description = <<-EOT
    Hard shutdown armed at boot on every machine, by the kernel itself.

    Google's budget alerts only send email; a paid account has no hard
    spending cap. This timer and the idle watcher are the only real
    protection against a forgotten cluster.
  EOT
  type        = number
  default     = 480
}

variable "idle_shutdown_minutes" {
  type    = number
  default = 30
}

variable "edge_version" {
  description = "Final Polygon Edge release, verified 7 Aug 2026. Archived, so it will not move."
  type        = string
  default     = "v1.3.2"
}

variable "chain_id" {
  type    = number
  default = 100100
}

variable "labels" {
  type = map(string)
  default = {
    project = "remittance-benchmarking"
    phase   = "phase-2"
    managed = "opentofu"
  }
}
