output "validator_public_ips" {
  description = "Public addresses of the validators. Used by the bootstrap script."
  value       = google_compute_instance.validator[*].network_interface[0].access_config[0].nat_ip
}

output "validator_private_ips" {
  description = <<-EOT
    Internal addresses. Validators talk to each other over these, so consensus
    traffic stays inside the cloud network rather than looping out to the
    public internet -- which matters from Phase 2, when the delay between
    regions is the thing being measured.
  EOT
  value       = google_compute_instance.validator[*].network_interface[0].network_ip
}

output "generator_public_ip" {
  description = "The machine that runs the measurement program. SSH here to start a benchmark."
  value       = google_compute_instance.generator.network_interface[0].access_config[0].nat_ip
}

output "rpc_url" {
  description = "Endpoint the harness sends payments to. Goes in config/phase1.json."
  value       = "http://${google_compute_instance.validator[0].network_interface[0].network_ip}:8545"
}

output "chain_id" {
  value = var.chain_id
}

output "zone" {
  description = "Read by scripts/bootstrap_cluster.sh to reach the machines."
  value       = var.zone
}

output "estimated_hourly_cost_usd" {
  description = <<-EOT
    Rough running cost, for sanity-checking against the real billing report.
    Spot list prices move, so treat this as an order-of-magnitude check rather
    than a quote -- the actual figure from the billing console is what feeds
    the budget conversation.
  EOT
  value = format(
    "~$%.2f/hour (%d validators + 1 generator, %s pricing)",
    var.use_spot
    ? (var.validator_count * 0.12 + 0.06)
    : (var.validator_count * 0.39 + 0.19),
    var.validator_count,
    var.use_spot ? "spot" : "on-demand",
  )
}

output "shutdown_guards" {
  description = "Confirm these before walking away from a running cluster."
  value = format(
    "hard shutdown at +%d minutes; idle shutdown after %d minutes without benchmark activity",
    var.max_lifetime_minutes,
    var.idle_shutdown_minutes,
  )
}

output "next_steps" {
  value = <<-EOT

    Cluster is up. Nothing is running on it yet.

      1. Bootstrap the chain (collects node identities, writes the shared
         genesis file, starts every validator):

           ./scripts/bootstrap_cluster.sh

      2. Deploy the test dollar and prepare the wallets:

           .venv/bin/python -m scripts.deploy_and_fund \
             --rpc-url <rpc_url above> \
             --chain-id ${var.chain_id} \
             --funder-key <premined key from bootstrap> \
             --senders 46

      3. Run the Phase 1 validation test (slow on purpose -- the goal is
         proving the pipeline records reality, not producing a number):

           .venv/bin/python -m harness.cli run \
             --config config/phase1.json --tps 5 --window 300 --amount 200

    WHEN FINISHED, run `tofu destroy`. The shutdown guards stop the machines
    but do not delete the disks, which keep billing. Only destroy removes
    everything.
  EOT
}
