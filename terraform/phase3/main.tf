/**
 * Phase 3 -- Lightning (LND on regtest against bitcoind).
 *
 * Deliberately parallel to terraform/phase2 rather than clever. The two
 * deployments must be describable in the paper as the same treatment applied
 * to different software: same four corridor regions, same generator placement,
 * same spot policy, same shutdown guards. Anything that differs between them
 * differs because Lightning genuinely differs, and each such difference is
 * justified in variables.tf.
 *
 * WHAT IS DIFFERENT FROM PHASE 2, AND WHY
 *
 *   4 hosts, 20 nodes   Lightning nodes are light enough to co-locate
 *                       (claude.md S5 #4). Node placement follows remittance
 *                       corridors so every measured payment crosses an ocean --
 *                       see harness/topology.py.
 *   bitcoind on host 0  Lightning settles channels on a Bitcoin chain. regtest
 *                       gives us a private one we mine ourselves, against
 *                       production Bitcoin Core rather than a simulator.
 *   smaller disks       No chain history exists to store.
 *   no tc impairment    Applied by scripts/inject_impairment.sh after boot, as
 *                       in phase 2, so the same impairment profile is reused.
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
  subnet_cidrs = { for i, r in var.regions : r.region => cidrsubnet("10.30.0.0/16", 8, i) }

  shutdown_guard = templatefile("${path.module}/../phase1/scripts/shutdown_guard.sh", {
    max_lifetime_minutes  = var.max_lifetime_minutes
    idle_shutdown_minutes = var.idle_shutdown_minutes
  })

  # Host 0 additionally runs bitcoind: it is the chain every LND node connects
  # to, so it must exist before any node can start.
  lightning_startup = [
    for i, r in var.regions : join("\n", [
      local.shutdown_guard,
      templatefile("${path.module}/scripts/lightning_setup.sh", {
        host_index       = i
        run_bitcoind     = i == 0 ? "yes" : "no"
        bitcoind_version = var.bitcoind_version
        lnd_version      = var.lnd_version
        nodes_per_host   = var.nodes_per_host
        bitcoind_host    = "10.30.0.10"
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

  generator_zone   = var.regions[var.generator_region_index].zone
  generator_region = var.regions[var.generator_region_index].region
}

# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

resource "google_compute_network" "bench" {
  name                    = "remittance-bench-p3"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "bench" {
  for_each      = local.subnet_cidrs
  name          = "remittance-bench-p3-${each.key}"
  ip_cidr_range = each.value
  region        = each.key
  network       = google_compute_network.bench.id
}

# Lightning peer-to-peer (9735+), LND REST (8080+), and bitcoind RPC/P2P
# (18443/18444). Ports are per-node offsets from these bases, so a range is
# opened rather than a list -- 5 nodes per host means 5 consecutive ports.
resource "google_compute_firewall" "internal" {
  name     = "remittance-bench-p3-internal"
  network  = google_compute_network.bench.name
  priority = 1000

  allow {
    protocol = "tcp"
    ports    = ["9735-9739", "8080-8084", "10009-10013", "18443-18444"]
  }
  allow { protocol = "udp" }
  allow { protocol = "icmp" }

  source_ranges = ["10.30.0.0/16"]
}

# SSH and REST for the operator only. Never open to the world: an exposed LND
# REST endpoint with a macaroon in reach is a funds-loss bug on mainnet, and
# leaving the habit here would be careless even though regtest coins are
# worthless.
resource "google_compute_firewall" "operator" {
  name     = "remittance-bench-p3-operator"
  network  = google_compute_network.bench.name
  priority = 1000

  allow {
    protocol = "tcp"
    ports    = ["22", "8080-8084"]
  }

  source_ranges = [var.operator_ip_cidr]
}

# ---------------------------------------------------------------------------
# Lightning hosts -- one per corridor region, several LND nodes each
# ---------------------------------------------------------------------------

resource "google_compute_instance" "lightning" {
  count        = length(var.regions)
  name         = "ln-host-${count.index}"
  machine_type = var.machine_type
  zone         = var.regions[count.index].zone

  # Names carry the corridor role so `gcloud compute instances list` reads as
  # the remittance story the paper tells, not as anonymous numbering.
  labels = {
    phase    = "phase3"
    corridor = replace(lower(var.regions[count.index].role), " ", "-")
  }

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = var.disk_size_gb
      type  = "pd-balanced"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.bench[var.regions[count.index].region].id
    # Host 0 holds bitcoind at a fixed address so every other host's LND
    # configuration can name it without a discovery step.
    network_ip = count.index == 0 ? "10.30.0.10" : null
    access_config {}
  }

  scheduling {
    provisioning_model          = local.spot.provisioning_model
    preemptible                 = local.spot.preemptible
    automatic_restart           = local.spot.automatic_restart
    on_host_maintenance         = local.spot.on_host_maintenance
    instance_termination_action = local.spot.instance_termination_action
  }

  metadata_startup_script = local.lightning_startup[count.index]

  metadata = {
    host-index     = tostring(count.index)
    corridor-role  = var.regions[count.index].role
    nodes-per-host = tostring(var.nodes_per_host)
  }

  allow_stopping_for_update = true
}

# ---------------------------------------------------------------------------
# Generator -- same size and same region as phase 2
# ---------------------------------------------------------------------------

resource "google_compute_instance" "generator" {
  name         = "ln-generator"
  machine_type = var.generator_machine_type
  zone         = local.generator_zone

  labels = { phase = "phase3", role = "generator" }

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

  scheduling {
    provisioning_model          = local.spot.provisioning_model
    preemptible                 = local.spot.preemptible
    automatic_restart           = local.spot.automatic_restart
    on_host_maintenance         = local.spot.on_host_maintenance
    instance_termination_action = local.spot.instance_termination_action
  }

  metadata_startup_script = local.generator_startup

  allow_stopping_for_update = true
}
