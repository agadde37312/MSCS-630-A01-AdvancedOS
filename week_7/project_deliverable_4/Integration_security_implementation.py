import os
import shlex
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

# --- File Class: Represents a file in our simulated system ---
class File:
    def __init__(self, name, content="", owner="root", group="root", permissions="rwxrwxrwx"):
        self.name = name
        self.content = content
        self.owner = owner
        self.group = group  # The group that owns this file
        self.permissions = permissions  # e.g., "rwxrwxrwx"

    def can_access(self, user, permission_type):
        """
        Checks if a user has a specific permission (read, write, execute) on the file.
        permission_type: 'r', 'w', 'x'
        Returns True if access is granted, False otherwise.
        """
        if user is None:
            return False  # No user, no access

        # Admin user has full access
        if user.role == "admin":
            return True

        # Owner permissions check
        if user.username == self.owner:
            perm_char_index = "rwx".find(permission_type)
            if perm_char_index != -1:
                return self.permissions[perm_char_index] == permission_type
            return False

        # Group permissions check
        if self.group in user.groups:
            perm_char_index = 3 + "rwx".find(permission_type)
            if perm_char_index != -1:
                return self.permissions[perm_char_index] == permission_type
            return False

        # Others permissions check
        perm_char_index = 6 + "rwx".find(permission_type)
        if perm_char_index != -1:
            return self.permissions[perm_char_index] == permission_type
        return False

# --- User Class: Represents a user in our simulated system ---
class User:
    def __init__(self, username, password, role="standard", groups=None):
        self.username = username
        self.password = password
        self.role = role  # e.g., "admin", "standard", "guest"
        # User's groups; default is their own username as a group
        self.groups = groups if groups is not None else [username]

# --- Simulated User Accounts ---
users = {
    "admin": User("admin", "adminpass", "admin", ["admin", "staff"]),
    "user1": User("user1", "user1pass", "standard", ["user1"]),
    "guest": User("guest", "guestpass", "guest", ["guest"])
}

current_user = None  # Stores the User object of the currently logged-in user

# --- Simulated File System ---
# A dictionary where keys are filenames and values are File objects
file_system = {
    "important_doc.txt": File("important_doc.txt", "This is an important document.\nOnly admin can modify.", "root", "root", "rw-r--r--"),
    "my_notes.txt": File("my_notes.txt", "Hello world from user1.\nMore lines here.", "user1", "user1", "rwxrwxr--"),
    "system_log.txt": File("system_log.txt", "System started successfully.\nError: Disk full. Another error.", "root", "root", "r--r--r--"),
    "executable_script.sh": File("executable_script.sh", "echo 'Script executed!'", "admin", "admin", "rwxr-x---"),
    "secret.txt": File("secret.txt", "Top secret info.", "admin", "admin", "rwx------")
}

# --- Command Implementations (Simulated File System interaction) ---
# Each command function takes args (list of strings) and optional input_data (string from pipe)
# and returns a string (output)

def cmd_ls(args, input_data=None):
    """Lists files with their permissions, owner, group, size, and name."""
    output = []

    files_to_list = []
    if not args:
        # If no arguments, list all files in the simulated file system
        files_to_list = file_system.values()
    else:
        # If arguments are provided, try to list specific files
        for arg in args:
            if arg in file_system:
                files_to_list.append(file_system[arg])
            else:
                output.append(f"ls: cannot access '{arg}': No such file or directory")

    for f in files_to_list:
        # Users can always see file metadata, but not necessarily content
        output.append(f"{f.permissions} {f.owner} {f.group} {len(f.content)} {f.name}")
    return "\n".join(output)

def cmd_cat(args, input_data=None):
    """Displays the content of a file, or passes piped input through."""
    output = []
    if input_data is not None:
        # If there's piped input, cat simply outputs it
        return input_data

    if not args:
        return "cat: missing operand"

    for filename in args:
        if filename in file_system:
            file_obj = file_system[filename]
            # Check if current user has read permission
            if file_obj.can_access(current_user, 'r'):
                output.append(file_obj.content)
            else:
                output.append(f"cat: {filename}: Permission denied")
        else:
            output.append(f"cat: {filename}: No such file or directory")
    return "\n".join(output)

def cmd_echo(args, input_data=None):
    """Prints text or redirects text to a file (overwrites)."""
    if not args:
        return ""

    # Check for redirection '>'
    if '>' in args:
        # Split the arguments around the '>'
        parts = " ".join(args).split('>', 1)
        content = parts[0].strip()
        filename = parts[1].strip()

        if not current_user:
            return "echo: Permission denied. Please log in."

        if filename in file_system:
            file_obj = file_system[filename]
            # Check if current user has write permission
            if file_obj.can_access(current_user, 'w'):
                file_obj.content = content  # Overwrite file content
                return ""  # No output on successful write
            else:
                return f"echo: {filename}: Permission denied"
        else:
            # If file does not exist, create it with default permissions for the current user
            # User must be logged in to create a file
            new_file = File(filename, content, current_user.username, current_user.groups[0], "rw-r--r--")
            file_system[filename] = new_file
            return ""
    else:
        # Normal echo: just return the arguments joined by spaces
        return " ".join(args)

def cmd_grep(args, input_data=None):
    """Filters lines from input data (or file) that contain a given pattern."""
    if not input_data:
        # If no piped input, try to read from a file if provided
        if len(args) == 2 and args[1] in file_system:
            filename = args[1]
            file_obj = file_system[filename]
            if file_obj.can_access(current_user, 'r'):
                input_data = file_obj.content
                pattern = args[0]
            else:
                return f"grep: {filename}: Permission denied"
        else:
            return "grep: no input provided or missing pattern/file"

    if not args:
        return "grep: missing pattern"

    pattern = args[0]
    # Split input data into lines
    lines = input_data.split('\n')

    matched_lines = []
    for line in lines:
        if pattern in line:
            matched_lines.append(line)
    return "\n".join(matched_lines)

def cmd_sort(args, input_data=None):
    """Sorts lines from input data alphabetically."""
    if not input_data:
        # If no piped input, try to read from a file if provided
        if len(args) == 1 and args[0] in file_system:
            filename = args[0]
            file_obj = file_system[filename]
            if file_obj.can_access(current_user, 'r'):
                input_data = file_obj.content
            else:
                return f"sort: {filename}: Permission denied"
        else:
            return "sort: no input provided"

    lines = input_data.split('\n')
    # Remove empty lines before sorting to prevent unexpected blank lines at the top
    lines = [line for line in lines if line.strip()]
    lines.sort()
    return "\n".join(lines)

def cmd_whoami(args, input_data=None):
    """Displays the username of the current user."""
    if current_user:
        return current_user.username
    return "Not logged in."

def cmd_touch(args, input_data=None):
    """Creates a new empty file or updates timestamp (simulated) of an existing one."""
    if not current_user: return "touch: Permission denied. Please log in."
    if not args:
        return "touch: missing file operand"
    filename = args[0]
    if filename not in file_system:
        # Create new file with current user as owner and default permissions
        new_file = File(filename, "", current_user.username, current_user.groups[0], "rw-r--r--")
        file_system[filename] = new_file
        return "" # No output on success
    else:
        # If file exists, simulate updating its timestamp (no actual timestamp changes)
        # Check if user has write permission to "touch" an existing file
        file_obj = file_system[filename]
        if file_obj.can_access(current_user, 'w'):
            return f"touch: '{filename}' updated."
        else:
            return f"touch: {filename}: Permission denied"

def cmd_rm(args, input_data=None):
    """Removes (deletes) a file."""
    if not current_user: return "rm: Permission denied. Please log in."
    if not args:
        return "rm: missing file operand"
    filename = args[0]
    if filename in file_system:
        file_obj = file_system[filename]
        # Only the owner or an admin user can delete a file
        if current_user.username == file_obj.owner or current_user.role == "admin":
            del file_system[filename]
            return "" # No output on success
        else:
            return f"rm: {filename}: Permission denied"
    else:
        return f"rm: {filename}: No such file or directory"

def cmd_chmod(args, input_data=None):
    """Changes file permissions. Usage: chmod <octal_permissions> <file>"""
    if not current_user: return "chmod: Please log in."
    if len(args) != 2:
        return "chmod: Usage: chmod <permissions> <file>"

    perm_str = args[0]
    filename = args[1]

    if filename not in file_system:
        return f"chmod: {filename}: No such file or directory"

    file_obj = file_system[filename]

    # Only the owner of the file or an admin user can change permissions
    if current_user.username != file_obj.owner and current_user.role != "admin":
        return f"chmod: {filename}: Operation not permitted"

    # Validate permission string: must be 3 digits and represent an octal number
    if not (len(perm_str) == 3 and perm_str.isdigit()):
        return "chmod: Invalid permission format. Use octal (e.g., 755)."

    try:
        octal_perm = int(perm_str, 8)  # Convert octal string to integer (base 8)

        # Convert the octal integer back to a 9-character rwx string
        new_perms_rwx = ""
        for i in range(3):  # Iterate for owner, group, and others
            val = (octal_perm >> (6 - 3 * i)) & 0b111  # Extract 3 bits for current segment (rwx)
            new_perms_rwx += "r" if (val & 0b100) else "-" # Read bit
            new_perms_rwx += "w" if (val & 0b010) else "-" # Write bit
            new_perms_rwx += "x" if (val & 0b001) else "-" # Execute bit

        file_obj.permissions = new_perms_rwx
        return "" # No output on success
    except ValueError:
        return "chmod: Invalid permission format. Use octal (e.g., 755)."

def cmd_chown(args, input_data=None):
    """Changes file ownership. Usage: chown <owner>[:<group>] <file>"""
    if not current_user: return "chown: Please log in."
    # Only admin users can change ownership
    if current_user.role != "admin":
        return "chown: Operation not permitted. Only admin can change ownership."

    if len(args) not in [2]: # Simplified: expecting <owner> <file> or <owner:group> <file>
        return "chown: Usage: chown <owner>[:<group>] <file>"

    owner_group_str = args[0]
    filename = args[1]

    if filename not in file_system:
        return f"chown: {filename}: No such file or directory"

    file_obj = file_system[filename]

    new_owner = None
    new_group = None

    if ':' in owner_group_str:
        # Handle owner:group format
        parts = owner_group_str.split(':')
        if len(parts) == 2:
            new_owner = parts[0]
            new_group = parts[1]
        else:
            return "chown: Invalid owner:group format."
    else:
        # Handle owner only format
        new_owner = owner_group_str
        new_group = file_obj.group # Keep existing group if not specified

    # Validate if new_owner is a known user
    if new_owner and new_owner not in users:
        return f"chown: Invalid user: '{new_owner}'"

    # Validate if new_group is a known 'group' (for simplicity, we assume known usernames can act as groups)
    # A more robust system would have a separate groups dictionary
    if new_group and new_group not in users and new_group not in [u.groups[0] for u in users.values() if u.groups]:
        return f"chown: Invalid group: '{new_group}'"

    if new_owner:
        file_obj.owner = new_owner
    if new_group:
        file_obj.group = new_group

    return "" # No output on success

# --- Command Dispatcher for Simulated Commands ---
simulated_commands = {
    "ls": cmd_ls,
    "cat": cmd_cat,
    "echo": cmd_echo,
    "grep": cmd_grep,
    "sort": cmd_sort,
    "whoami": cmd_whoami,
    "touch": cmd_touch,
    "rm": cmd_rm,
    "chmod": cmd_chmod,
    "chown": cmd_chown
}

def execute_single_command(command_name, args, input_data=None):
    """
    Executes a single command, prioritizing simulated commands.
    If not simulated, attempts to execute as an external OS command.
    """
    if command_name in simulated_commands:
        # Execute simulated command
        return simulated_commands[command_name](args, input_data)
    else:
        # Attempt to run as an external OS command (does not interact with simulated file system)
        if input_data is not None:
            # If there's piped input for an external command, write to a temp file
            # This is a simplification; real shells use pipes
            with open("temp_pipe_input.txt", "w") as f:
                f.write(input_data)
            args = ["temp_pipe_input.txt"] + args # Prepend temp file to args
            # Note: External commands won't typically read from stdin this way,
            # but for this simulation, we're making it work for simpler cases.
            # A true pipe for external commands would involve more complex os.pipe() usage.

        try:
            # Capture stdout from external command
            import subprocess
            process = subprocess.run([command_name] + args, capture_output=True, text=True, check=True)
            return process.stdout.strip()
        except FileNotFoundError:
            return f"Command not found: {command_name}"
        except subprocess.CalledProcessError as e:
            return f"Error executing {command_name}: {e.stderr.strip()}"
        except Exception as e:
            return f"An unexpected error occurred during external command execution: {e}"
        finally:
            if os.path.exists("temp_pipe_input.txt"):
                os.remove("temp_pipe_input.txt")


def parse_and_execute_pipeline(full_command_line):
    """
    Parses a full command line, handling pipes, and executes commands sequentially.
    Manages input/output redirection between piped commands.
    """
    global current_user

    # Split the full command line by '|' to get individual commands in the pipeline
    command_parts = full_command_line.split('|')

    current_input = None  # This will hold the output of the previous command in the pipeline

    for i, cmd_str in enumerate(command_parts):
        cmd_str = cmd_str.strip()
        if not cmd_str:
            return "Syntax error: Empty command in pipeline."

        # Use shlex.split to correctly parse arguments, especially with spaces and quotes
        try:
            parts = shlex.split(cmd_str)
        except ValueError as e:
            return f"Syntax error in command '{cmd_str}': {e}"

        command_name = parts[0]
        args = parts[1:]

        # Execute the current command, passing the output of the previous as input
        result = execute_single_command(command_name, args, current_input)

        # If an error occurs (e.g., "Command not found", "Permission denied"),
        # stop the pipeline and return the error immediately.
        # Check for common error messages returned by our simulated commands or external execution
        if result and ("Command not found" in result or "Permission denied" in result or "No such file or directory" in result or "Usage:" in result or "Error executing" in result):
            return result

            # The result of the current command becomes the input for the next
        current_input = result

    return current_input # Return the final output of the pipeline


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
    if evicted in pages_in_memory[pid]: # Ensure it's still there before removing
        pages_in_memory[pid].remove(evicted)


# -------------------------------
# Process class to represent simulated processes
# -------------------------------
class Process:
    def __init__(self, pid, name, command_line, burst_time, duration, priority=1, arrival_time=None):
        self.pid = pid
        self.name = name
        self.command_line = command_line  # full command as string
        # Ensure command_line is a string before splitting
        self.command = command_line.split()[0] if isinstance(command_line, str) and command_line else ""
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
# Handle built-in commands (non-file system, non-piping related)
# -------------------------------
def run_other_builtin(command, args):
    """
    Check and execute built-in shell commands that are not related to file system
    or piping (e.g., cd, pwd, kill, scheduler commands).
    Return True if handled here, False if command is external or handled by piping.
    """
    global jobs, job_id_counter, scheduler, process_id_counter

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

    elif command == 'clear':
        # Clear the terminal screen by calling system 'clear'
        os.system('clear')

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
            # cmd_line, burst_time, duration, priority
            proc = Process(pid, command_line, command_line, total_time, total_time, priority) # name=command_line for simplicity
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
        return False  # Not a built-in command handled here

    return True  # Built-in command handled

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
    if evicted in pages_in_memory[pid]: # Ensure it's still there before removing
        pages_in_memory[pid].remove(evicted)


# -------------------------------
# Testing Commands
# -------------------------------
def run_memory_test():
    global memory, pages_in_memory, page_faults, page_access_times
    memory.clear()
    pages_in_memory.clear()
    page_faults.clear()
    page_access_times.clear()

    # Use existing Process class, but adapt command_line argument
    processes = [Process(pid=i, name=f"p{i}", command_line=f"proc{i} 1 1", burst_time=2, duration=2) for i in range(5)]
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
# Main shell loop
# -------------------------------
def shell_loop():
    """
    Main loop that repeatedly prompts for input and executes commands.
    Handles login/logout, keyboard interrupts, and EOF to exit gracefully.
    """
    global current_user

    while True:
        # If no user is logged in, prompt for login
        if not current_user:
            print("\n--- Simulated Shell ---")
            print("Please log in. Usage: login <username> <password>")
            print("Available users: admin (pass: adminpass), user1 (pass: user1pass), guest (pass: guestpass)")
            command_line = input("> ")

            if command_line.lower() == "exit":
                print("Exiting shell.")
                sys.exit(0)

            # Special handling for login command outside the main pipeline
            if command_line.strip().startswith("login"):
                parts = shlex.split(command_line)
                if len(parts) == 3:  # Expecting "login <username> <password>"
                    username = parts[1]
                    password = parts[2]
                    if username in users and users[username].password == password:
                        current_user = users[username]
                        print(f"Logged in as {username}.")
                    else:
                        print("Login failed: Invalid username or password.")
                else:
                    print("Usage: login <username> <password>")
            else:
                print("Please log in to use other commands.")
            continue # Continue the loop to re-prompt for login

        # If a user is logged in, show the prompt
        try:
            command_line = input(f"{current_user.username}@simulated_shell$ ")

            # Handle built-in shell commands like exit and logout
            if command_line.lower() == "exit":
                print("Exiting shell.")
                sys.exit(0) # Exit the entire script
            elif command_line.lower() == "logout":
                print("Logging out...")
                current_user = None # Clear current user
                continue # Go back to login prompt

            # Try to handle as a non-file-system built-in command first
            tokens = shlex.split(command_line)
            if tokens and run_other_builtin(tokens[0], tokens[1:]):
                continue # If handled, go to next prompt

            # Otherwise, parse and execute the command line, including any pipes
            output = parse_and_execute_pipeline(command_line)

            # Print the output of the command/pipeline if there is any
            if output is not None and output != "":
                print(output)
        except KeyboardInterrupt:
            # Ctrl+C pressed: print message but don't exit shell
            print("\nUse 'exit' to quit the shell.")
        except EOFError:
            # Ctrl+D pressed: exit shell cleanly
            print("\nExiting shell.")
            sys.exit(0) # Exit the entire script
        except Exception as e:
            # Catch any unexpected errors during command execution
            print(f"An unexpected error occurred: {e}")

# Start the shell when the script is run directly
if __name__ == "__main__":
    shell_loop()
