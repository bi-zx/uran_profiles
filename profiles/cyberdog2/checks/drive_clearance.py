#!/usr/bin/env python3
"""Read body-centred clearance from a live scan without a motion publisher."""
import argparse
from collections import Counter
import json
from pathlib import Path
import statistics
import time

import rclpy
from rclpy.qos import qos_profile_sensor_data
from rclpy.time import Time
from sensor_msgs.msg import LaserScan
from tf2_ros import Buffer, TransformException, TransformListener
from uran_navigation_plugin.depth_scan_adapter import VirtualLaserScan
from uran_navigation_plugin.obstacle_avoidance import GapAvoidancePlanner
from uran_ros2_adapter.map_geometry import rigid, scan_in_body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("topics", nargs="+", metavar="scan_topic")
    parser.add_argument("--body-frame", default="base_link")
    parser.add_argument("--seconds", type=float, default=4.0)
    args = parser.parse_args()
    config = json.loads((Path(__file__).resolve().parents[1]/"autotask.json").read_text())["straight_drive"]
    planners = {topic: GapAvoidancePlanner(config) for topic in args.topics}
    # At rest the normal controller includes its stopping margin in the forward horizon.
    results = {topic: (Counter(), Counter(), []) for topic in args.topics}
    rclpy.init(args=[])
    node = rclpy.create_node("drive_clearance_reader")
    tf = Buffer()
    listener = TransformListener(tf, node)

    def scan(msg, topic):
        planner = planners[topic]
        counts, turns, front = results[topic]
        try:
            transform = tf.lookup_transform(args.body_frame, msg.header.frame_id, Time.from_msg(msg.header.stamp))
        except TransformException:
            return
        value = scan_in_body(msg, *rigid(transform.transform))
        observed = VirtualLaserScan.from_observation(value)
        direct = planner.plan(observed, stop_distance_m=planner.min_stop_distance_m + config.get("stop_margin_m", 0.25))
        counts[direct.reason] += 1
        turns[planner.plan(observed, turn_only=True).reason] += 1
        front.append(direct.front_clearance_m)

    for topic in args.topics:
        node.create_subscription(LaserScan, topic, lambda msg, t=topic: scan(msg, t), qos_profile_sensor_data)
    try:
        end = time.monotonic() + args.seconds
        while time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=0.1)
    finally:
        node.destroy_node()
        rclpy.shutdown()
    for topic, (counts, turns, front) in results.items():
        planner = planners[topic]
        print(json.dumps(dict(topic=topic, frames=len(front), required_width_m=planner.min_gap_physical_width_m,
                              turn_radius_m=planner.turn_radius_m, forward=dict(counts), scan_only_turn=dict(turns),
                              median_forward_m=statistics.median(front) if front else None)))
    return 0 if any(front for _, _, front in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
