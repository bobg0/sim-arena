from ops.ec2_workers import LaunchConfig, CleanupConfig, launch_workers, cleanup_workers

launch = launch_workers(
    LaunchConfig(
        count=2,
        region="us-east-2",
        security_group_ids=["sg-06cddec780dfbdae4"],
        subnet_id="subnet-09f1a971bd8077ea7",
        bootstrap_secret=True,
        wait_ssh=True,
    )
)

# launch.instances contains structured worker metadata.

cleanup_workers(
    CleanupConfig(
        action="terminate",
        region=launch.region,
        inventory_file=launch.inventory_path,
        require_confirmation=False,
    )
)