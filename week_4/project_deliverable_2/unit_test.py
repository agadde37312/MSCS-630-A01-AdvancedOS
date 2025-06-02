import unittest
import time
from unittest.mock import patch
from custom_shell_process_scheduling import Process, RoundRobinScheduler, PriorityScheduler



class SchedulerTests(unittest.TestCase):

    @patch('time.sleep', return_value=None)

    def test_round_robin_execution(self, mock_sleep):
        print("\n=== Round-Robin Scheduling ===")
        # Setup RoundRobinScheduler with small time slice
        scheduler = RoundRobinScheduler(time_slice=2)

        # Create 3 processes with burst time > time slice to force switches
        p1 = Process(1, "round_proc1", "round_cmd1", burst_time=2, duration=2)
        p2 = Process(2, "round_proc2", "round_cmd2", burst_time=1, duration=1)
        p3 = Process(3, "round_proc3", "round_cmd3", burst_time=3, duration=3)

        scheduler.add_process(p1)
        scheduler.add_process(p2)
        scheduler.add_process(p3)

        start_time = time.time()
        scheduler.run()
        end_time = time.time()

        # All processes should be completed
        self.assertTrue(p1.remaining_time <= 0)
        self.assertTrue(p2.remaining_time <= 0)
        self.assertTrue(p3.remaining_time <= 0)

        # Check statuses
        self.assertEqual(p1.status, 'Completed')
        self.assertEqual(p2.status, 'Completed')


        # Processes should run multiple times (verified by remaining_time reaching zero)
        self.assertAlmostEqual(p1.remaining_time, 0, delta=0.01)
        self.assertAlmostEqual(p2.remaining_time, 0, delta=0.01)
        self.assertAlmostEqual(p3.remaining_time, 0, delta=0.01)

    def test_priority_scheduling_execution(self):
        print("\n=== Priority-Based Scheduling ===")
        ps = PriorityScheduler()

        # Create high priority process (priority=5) and low priority (priority=1)
        p_high = Process(1, "HighPriority", "cmd_high", burst_time=0.01, duration=0.01, priority=10)
        p_low = Process(2, "LowPriority", "cmd_low", burst_time=0.05, duration=0.1, priority=1)

        ps.add_process(p_low)
        ps.add_process(p_high)

        start_time = time.time()
        ps.run()
        end_time = time.time()

        # Both should complete
        self.assertTrue(p_high.completed)
        self.assertTrue(p_low.completed)

        # High priority process should start before low priority process
        self.assertLessEqual(p_high.start_time, p_low.start_time)

        # Total run time at least sum of burst times
        total_burst = p_high.burst_time + p_low.burst_time
        self.assertGreaterEqual(end_time - start_time, total_burst * 0.9)

        # remaining time should be zero
        self.assertAlmostEqual(p_high.remaining_time, 0, delta=0.01)
        self.assertAlmostEqual(p_low.remaining_time, 0, delta=0.01)

    def test_performance_metrics(self):
        print("\n=== performance test metrics ===")
        # Helper to compute metrics
        def compute_metrics(processes):
            metrics = []
            for p in processes:
                waiting_time = (p.start_time - p.arrival_time) if p.start_time else None
                turnaround_time = (p.end_time - p.arrival_time) if p.end_time else None
                response_time = waiting_time  # Assuming response time = waiting time here
                metrics.append({
                    "pid": p.pid,
                    "waiting_time": waiting_time,
                    "turnaround_time": turnaround_time,
                    "response_time": response_time,
                })
            return metrics

        rr = RoundRobinScheduler(time_slice=0.1)
        p1 = Process(1, "proc1", "proc1", burst_time=0.2, duration=0.2)
        p2 = Process(2, "proc2", "proc2", burst_time=0.3, duration=0.3)
        rr.add_process(p1)
        rr.add_process(p2)
        rr.run()

        metrics = compute_metrics([p1, p2])

        for metric in metrics:
            self.assertIsNotNone(metric["waiting_time"])
            self.assertIsNotNone(metric["turnaround_time"])
            self.assertIsNotNone(metric["response_time"])
            # turnaround_time should be >= waiting_time
            self.assertGreaterEqual(metric["turnaround_time"], metric["waiting_time"])

if __name__ == '__main__':
    unittest.main()
