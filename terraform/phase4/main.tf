/**
 * Phase 4 -- NEAR (nearcore, Nightshade sharding) on a private network.
 *
 * Deliberately parallel to phases 2 and 3: same four corridor regions, same
 * generator placement and size, same shutdown guards. The three-way comparison
 * is only fair if every architecture paid the same geographic latency, so
 * anything that differs here differs because NEAR genuinely differs, and each
 * difference is justified in variables.tf.
 *
 * WHAT IS DIFFERENT, AND WHY
 *
 *   8 validators        Set by quota, not preference. 12 needs 104 vCPU
 *                       against a 96 ceiling; a request for 144 was denied.
 *                       8 gives exactly 2 validators per shard and no margin.
 *   4 shards, pinned    Must match `expected_shards` in the adapter. A chain
 *                       that comes up unsharded would measure sharding that is
 *                       not happening.
 *   spot validators,    A reclaimed validator costs one node. A reclaimed
 *   on-demand generator generator stops all collection and nothing restarts
 *                       it -- learned the hard way in phase 3.
 *   larger disks        NEAR's state is heavier than Polygon Edge's, though
 *                       still nothing like the 1 TB mainnet history figure.
 */

terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.regions[0].region
  zone    = var.regions[0].zone
}

locals {
  subnet_cidrs = { for i, r in var.regions : r.region => cidrsubnet("10.40.0.0/16", 8, i) }

  # One flat list of validators, two per region, so index arithmetic stays
  # simple in the bootstrap script and in harness/topology-style placement.
  validators = flatten([
    for ri, r in var.regions : [
      for vi in range(var.validators_per_region) : {
        index  = ri * var.validators_per_region + vi
        region = r.region
        zone   = r.zone
        role   = r.role
      }
    ]
  ])

  shutdown_guard = templatefile("${path.module}/../phase1/scripts/shutdown_guard.sh", {
    max_lifetime_minutes  = var.max_lifetime_minutes
    idle_shutdown_minutes = var.idle_shutdown_minutes
  })

  validator_startup = [
    for v in local.validators : join("\n", [
      local.shutdown_guard,
      templatefile("${path.module}/scripts/near_setup.sh", {
        validator_index = v.index
        num_validators  = length(local.validators)
        num_shards      = var.num_shards
        near_version    = var.near_version
        boot_node_ip    = "10.40.0.10"
      }),
    ])
  ]

  generator_startup = join("\n", [
    local.shutdown_guard,
    file("${path.module}/../phase1/scripts/generator_setup.sh"),
  ])

  spot = var.use_spot ? {
    provisioning_model          = "SPOT"
    preemptible                 = true
    automatic_restart           = false
    on_host_maintenance         = "TERMINATE"
    instance_termination_action = "STOP"
    } : {
    provisioning_model          = "STANDARD"
    preemptible                 = false
    automatic_restart           = true
    on_host_maintenance         = "MIGRATE"
    instance_termination_action = null
  }

  generator_zone   = var.regions[0].zone
  generator_region = var.regions[0].region
}

# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

resource "google_compute_network" "bench" {
  name                    = "remittance-bench-p4"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "bench" {
  for_each      = local.subnet_cidrs
  name          = "remittance-bench-p4-${each.key}"
  ip_cidr_range = each.value
  region        = each.key
  network       = google_compute_network.bench.id
}

# 24567 is nearcore's peer-to-peer port, 3030 its JSON-RPC. Both are needed
# between validators: peers gossip on 24567, and the generator reaches the
# chain on 3030.
resource "google_compute_firewall" "internal" {
  name     = "remittance-bench-p4-internal"
  network  = google_compute_network.bench.name
  priority = 1000

  allow {
    protocol = "tcp"
    ports    = ["24567", "3030", "3031"]
  }
  allow { protocol = "udp" }
  allow { protocol = "icmp" }

  source_ranges = ["10.40.0.0/16"]
}

# SSH and RPC for the operator only. An open NEAR RPC endpoint is found by
# scanners within hours, exactly as an open chain endpoint was in phase 2.
resource "google_compute_firewall" "operator" {
  name     = "remittance-bench-p4-operator"
  network  = google_compute_network.bench.name
  priority = 1000

  allow {
    protocol = "tcp"
    ports    = ["22", "3030"]
  }

  source_ranges = [var.operator_ip_cidr]
}

# ---------------------------------------------------------------------------
# Validators -- two per corridor region
# ---------------------------------------------------------------------------

resource "google_compute_instance" "validator" {
  count        = length(local.validators)
  name         = "near-validator-${count.index}"
  machine_type = var.machine_type
  zone         = local.validators[count.index].zone

  labels = {
    phase    = "phase4"
    corridor = replace(lower(local.validators[count.index].role), " ", "-")
  }

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = var.disk_size_gb
      type  = "pd-balanced"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.bench[local.validators[count.index].region].id
    # Validator 0 is the boot node at a fixed address, so every other node can
    # name a peer without a discovery step.
    network_ip = count.index == 0 ? "10.40.0.10" : null
    access_config {}
  }

  scheduling {
    provisioning_model          = local.spot.provisioning_model
    preemptible                 = local.spot.preemptible
    automatic_restart           = local.spot.automatic_restart
    on_host_maintenance         = local.spot.on_host_maintenance
    instance_termination_action = local.spot.instance_termination_action
  }

  metadata_startup_script = local.validator_startup[count.index]

  metadata = {
    validator-index = tostring(count.index)
    corridor-role   = local.validators[count.index].role
    num-shards      = tostring(var.num_shards)
  }

  allow_stopping_for_update = true
}

# ---------------------------------------------------------------------------
# Generator -- on demand, deliberately
# ---------------------------------------------------------------------------

resource "google_compute_instance" "generator" {
  name         = "near-generator"
  machine_type = var.generator_machine_type
  zone         = local.generator_zone

  labels = { phase = "phase4", role = "generator" }

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = var.disk_size_gb
      type  = "pd-balanced"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.bench[local.generator_region].id
    access_config {}
  }

  # NOT spot, unlike the validators. Phase 3 lost a generator to preemption
  # mid-deployment; a reclaimed spot instance stays STOPPED, so data collection
  # halts and nothing restarts it. About $0.27/hr more for the one machine
  # whose loss stops everything.
  scheduling {
    provisioning_model  = "STANDARD"
    preemptible         = false
    automatic_restart   = true
    on_host_maintenance = "MIGRATE"
  }

  metadata_startup_script = local.generator_startup

  allow_stopping_for_update = true
}
