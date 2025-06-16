import os
import sys
import signal
import time
import heapq
import itertools
import threading
from collections import deque, OrderedDict, defaultdict
from queue import Queue

# -------------------------------
# Constants for Paging System
# -------------------------------
PAGE_SIZE = 4
TOTAL_PAGES = 16

# -------------------------------
# Memory and Page Tracking
# -------------------------------
memory = deque()  # Stores (pid, page_number)
pages_in_memory = defaultdict(list)
page_faults = defaultdict(int)
page_access_times = {}  # (pid, page_number) -> timestamp
replacement_policy = 'FIFO'  # or 'LRU'

# -------------------------------
# Producer-Consumer Synchronization
# -------------------------------
buffer = Queue(maxsize=5)
buffer_lock = threading.Lock()
empty_slots = threading.Semaphore(5)
full_slots = threading.Semaphore(0)



# -------------------------------
# Simulate memory access and page replacement
# -------------------------------
def simulate_memory_access(pid):
    pages_needed = 2
    current_time = time.time()
    for page_number in range(pages_needed):
        page = (pid, page_number)
        if page not in memory:
            page_faults[pid] += 1
            if len(memory) >= TOTAL_PAGES:
                evict_page()
            memory.append(page)
            pages_in_memory[pid].append(page)
        page_access_times[page] = current_time

def evict_page():
    if replacement_policy == 'FIFO':
        evicted = memory.popleft()
    elif replacement_policy == 'LRU':
        evicted = min(memory, key=lambda p: page_access_times.get(p, 0))
        memory.remove(evicted)
    pid, _ = evicted
    pages_in_memory[pid].remove(evicted)


# -------------------------------
# Process class to represent simulated processes
# -------------------------------
class Process:
    def __init__(self, pid, name,  command_line, burst_time, duration, priority=1, arrival_time=None):
        self.pid = pid
        self.name = name
        self.command_line = command_line  # full command as string
        self.command = command_line.split()[0]  # first word = command
        self.burst_time = burst_time
        self.duration = duration
        self.priority = priority
        self.arrival_time = arrival_time if arrival_time is not None else time.time()
        self.remaining_time = burst_time
        self.completed = False
        self.start_time = None
        self.end_time = None

    def run(self, time_slice):
        actual_run = min(time_slice, self.remaining_time)
        print(f"Process {self.pid} running for {actual_run}s; remaining before run: {self.remaining_time}")
        time.sleep(0.02)  # Simulate work with minimal sleep for unit test speed-up
        self.remaining_time -= actual_run
        print(f"Process {self.pid} remaining time after run: {self.remaining_time}")
        if self.remaining_time <= 0:
            self.completed = True
            self.end_time = time.time()
            print(f"Process {self.pid} marked as completed")
        if self.start_time is None:
            self.start_time = time.time()





# -------------------------------
# Round-Robin Scheduler class
# -------------------------------
class RoundRobinScheduler:
    def __init__(self, time_slice=2):
        self.queue = deque()                # Queue to hold processes in round-robin order
        self.time_slice = time_slice        # Time slice (quantum) for each process

    def add_process(self, process):
        self.queue.append(process)          # Add a new process to the end of the queue

    def run(self):
        while self.queue:
            process = self.queue.popleft()
            print(f"Running process {process.pid}: {process.command_line}")
            process.status = 'Running'
            run_time = min(self.time_slice, process.remaining_time)
            process.run(run_time)  # This sets start_time and end_time properly
            if process.completed:
                process.status = 'Completed'
                print(f"Process {process.pid} completed.")
            else:
                process.status = 'Waiting'
                print(f"Process {process.pid} paused, {process.remaining_time}s remaining.")
                self.queue.append(process)



# -------------------------------
# Priority-Based Scheduler class
# -------------------------------
class PriorityScheduler:
    def __init__(self):
        self.process_heap = []  # store as class attribute for testing

    def add_process(self, process):
        # Negative priority because heapq is min-heap
        heapq.heappush(self.process_heap, (-process.priority, process.arrival_time, process))



    def run(self):
        while self.process_heap:
            _, _, process = heapq.heappop(self.process_heap)
            print(f"Running process {process.pid} (priority {process.priority})")
            process.status = 'Running'

            process.run(process.remaining_time)  # Run until completion
            #process.remaining_time = 0
            assert process.completed
            print(f"Process {process.pid} completed.")

# -------------------------------
# Producer-Consumer Threads
# -------------------------------
def producer():
    for i in range(10):
        empty_slots.acquire()
        with buffer_lock:
            buffer.put(f"item-{i}")
            print(f"Produced: item-{i}")
        full_slots.release()
        time.sleep(0.01)

def consumer():
    for i in range(10):
        full_slots.acquire()
        with buffer_lock:
            item = buffer.get()
            print(f"Consumed: {item}")
        empty_slots.release()
        time.sleep(0.01)

# -------------------------------
# Shell global state
# -------------------------------
jobs = {}                                      # Background jobs: {job_id: (pid, command, status)}
job_id_counter = 1                             # Incrementing job ID
scheduler = None                               # Current scheduler (RoundRobinScheduler or PriorityScheduler)
process_id_counter = itertools.count(1)        # Unique process IDs

# -------------------------------
# Handle built-in commands
# -------------------------------
def run_builtin(command, args):
    """
    Check and execute built-in shell commands.
    Return True if handled here, False if command is external.
    """
    global jobs, job_id_counter

    if command == 'cd':
        # Change current directory to specified path or home if none given
        try:
            path = args[0] if args else os.path.expanduser('~')
            os.chdir(path)
        except Exception as e:
            print(f"cd: {e}")

    elif command == 'pwd':
        # Print current working directory
        print(os.getcwd())

    elif command == 'exit':
        # Exit the shell program
        print("Exiting shell.")
        sys.exit(0)

    elif command == 'echo':
        # Print the given arguments to the terminal
        print(' '.join(args))

    elif command == 'clear':
        # Clear the terminal screen by calling system 'clear'
        os.system('clear')

    elif command == 'ls':
        # List files and directories in current directory
        try:
            files = os.listdir('.')
            for f in files:
                print(f)
        except Exception as e:
            print(f"ls: {e}")

    elif command == 'cat':
        # Display the contents of one or more files
        if not args:
            print("cat: missing filename")
        else:
            for filename in args:
                try:
                    with open(filename, 'r') as file:
                        print(file.read(), end='')
                except Exception as e:
                    print(f"cat: {filename}: {e}")

    elif command == 'mkdir':
        # Create a new directory (including parents if necessary)
        if not args:
            print("mkdir: missing directory name")
        else:
            try:
                os.makedirs(args[0], exist_ok=True)
            except Exception as e:
                print(f"mkdir: {e}")

    elif command == 'rmdir':
        # Remove an empty directory
        if not args:
            print("rmdir: missing directory name")
        else:
            try:
                os.rmdir(args[0])
            except Exception as e:
                print(f"rmdir: {e}")

    elif command == 'rm':
        # Remove a file
        if not args:
            print("rm: missing file name")
        else:
            try:
                os.remove(args[0])
            except Exception as e:
                print(f"rm: {e}")

    elif command == 'touch':
        # Create an empty file or update the last modified time
        if not args:
            print("touch: missing file name")
        else:
            try:
                with open(args[0], 'a'):
                    os.utime(args[0], None)
            except Exception as e:
                print(f"touch: {e}")

    elif command == 'kill':
        # Kill a process by PID
        if not args:
            print("kill: missing PID")
        else:
            try:
                pid = int(args[0])
                os.kill(pid, signal.SIGTERM)
            except Exception as e:
                print(f"kill: {e}")

    elif command == 'jobs':
        # List background jobs
        for jid, (pid, cmd, status) in jobs.items():
            print(f"[{jid}] PID: {pid} Status: {status} Command: {cmd}")

    elif command == 'fg':
        # Bring background job to foreground by job ID and wait for it to finish
        if not args:
            print("fg: missing job ID")
        else:
            try:
                jid = int(args[0])
                if jid in jobs:
                    pid, cmd, status = jobs[jid]
                    print(f"Bringing job [{jid}] to foreground: {cmd}")
                    os.waitpid(pid, 0)  # Wait for the process to complete
                    jobs.pop(jid)  # Remove job from tracking after completion
                else:
                    print(f"fg: no such job [{jid}]")
            except Exception as e:
                print(f"fg: {e}")

    elif command == 'bg':
        # Resume a stopped background job
        if not args:
            print("bg: missing job ID")
        else:
            try:
                jid = int(args[0])
                if jid in jobs:
                    pid, cmd, status = jobs[jid]
                    os.kill(pid, signal.SIGCONT)  # Continue the stopped process
                    jobs[jid] = (pid, cmd, 'Running')  # Update job status
                    print(f"Resumed job [{jid}] in background: {cmd}")
                else:
                    print(f"bg: no such job [{jid}]")
            except Exception as e:
                print(f"bg: {e}")

    elif command == 'schedule':
        # Select scheduler type
        if not args:
            print("Usage: schedule rr <time_slice> OR schedule priority")
        elif args[0] == 'rr':
            if len(args) < 2:
                print("schedule rr <time_slice>")
            else:
                time_slice = int(args[1])
                scheduler = RoundRobinScheduler(time_slice)
                print(f"Switched to Round-Robin Scheduler (time slice {time_slice}s)")
        elif args[0] == 'priority':
            scheduler = PriorityScheduler()
            print("Switched to Priority-Based Scheduler")
        else:
            print("Unknown scheduler type.")

    elif command == 'addproc':
        # Add a simulated process
        if scheduler is None:
            print("No scheduler selected. Use 'schedule' command first.")
        elif len(args) < 3:
            print("Usage: addproc <command_line> <priority> <total_time>")
        else:
            command_line = args[0]
            priority = int(args[1])
            total_time = int(args[2])
            pid = next(process_id_counter)
            proc = Process(pid, command_line, priority, total_time)
            scheduler.add_process(proc)
            print(f"Added process {pid}: {command_line} (priority {priority}, total time {total_time}s)")

    elif command == 'run':
        # Start running the scheduler
        if scheduler is None:
            print("No scheduler selected. Use 'schedule' command first.")
        else:
            print("Starting scheduler...")
            scheduler.run()

    elif command == 'memtest':
        run_memory_test()
        return True

    elif command == 'synctest':
        run_sync_test()
        return True

    elif command.startswith('policy'):
        parts = command.split()
        if len(parts) == 2 and parts[1] in ("FIFO", "LRU"):
            global replacement_policy
            replacement_policy = parts[1]
            print(f"Policy set to {replacement_policy}")
        else:
            print("Usage: policy FIFO|LRU")
        return True



    else:
        return False  # Not a built-in command

    return True  # Built-in command handled


# -------------------------------
# Execute command (built-in or external)
# -------------------------------
def execute_command(command_line):
    """
    Parse the command line, determine background or foreground,
    execute built-in or external commands accordingly.
    """
    global jobs, job_id_counter

    tokens = command_line.strip().split()
    if not tokens:
        return

    # Detect background execution symbol '&' at end of command
    background = False
    if tokens[-1] == '&':
        background = True
        tokens = tokens[:-1]  # Remove '&' from tokens

    command = tokens[0]
    args = tokens[1:]

    # First try to execute built-in commands
    if run_builtin(command, args):
        return

    # Handle external (non-built-in) commands
    try:
        pid = os.fork()  # Fork current process
        if pid == 0:
            # Child process: replace process image with new command
            try:
                os.execvp(command, [command] + args)
            except FileNotFoundError:
                print(f"{command}: command not found")
            except Exception as e:
                print(f"Error executing {command}: {e}")
            os._exit(1)  # Exit child on failure
        else:
            # Parent process
            if background:
                # Add job to background job list and print job info
                jobs[job_id_counter] = (pid, command_line, 'Running')
                print(f"[{job_id_counter}] {pid}")
                job_id_counter += 1
            else:
                # Wait for child process to complete (foreground)
                os.waitpid(pid, 0)
    except Exception as e:
        print(f"Error executing command: {e}")

# -------------------------------
# Main shell loop
# -------------------------------
def shell_loop():
    """
    Main loop that repeatedly prompts for input and executes commands.
    Handles keyboard interrupts and EOF to exit gracefully.
    """
    while True:
        try:
            # Display shell prompt and read command line input
            command_line = input("shell> ")
            execute_command(command_line)
        except KeyboardInterrupt:
            # Ctrl+C pressed: print message but don't exit shell
            print("\nUse 'exit' to quit the shell.")
        except EOFError:
            # Ctrl+D pressed: exit shell cleanly
            print("\nExiting shell.")
            break

# -------------------------------
# Testing Commands
# -------------------------------
def run_memory_test():
    global memory, pages_in_memory, page_faults, page_access_times
    memory.clear()
    pages_in_memory.clear()
    page_faults.clear()
    page_access_times.clear()

    processes = [Process(pid=i, name=f"p{i}", command_line=f"proc{i}", burst_time=2, duration=2) for i in range(5)]
    rr = RoundRobinScheduler(time_slice=1)
    for p in processes:
        rr.add_process(p)
    rr.run()


# -------------------------------
# Run Synchronization Test
# -------------------------------
def run_sync_test():
    t1 = threading.Thread(target=producer)
    t2 = threading.Thread(target=consumer)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

# -------------------------------
# Start the shell
# -------------------------------
if __name__ == '__main__':
    shell_loop()
