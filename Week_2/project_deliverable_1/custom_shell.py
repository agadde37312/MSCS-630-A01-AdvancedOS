import os
import sys
import signal

# Dictionary to track background jobs:
# key = job_id, value = (pid, command_line, status)
jobs = {}
job_id_counter = 1  # Unique job ID counter

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
        # Send SIGTERM to process with given PID
        if not args:
            print("kill: missing PID")
        else:
            try:
                pid = int(args[0])
                os.kill(pid, signal.SIGTERM)
            except Exception as e:
                print(f"kill: {e}")

    elif command == 'jobs':
        # List all currently tracked background jobs
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
        # Resume a stopped background job by sending SIGCONT signal
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

    else:
        # Not a built-in command
        return False

    return True

def execute_command(command_line):
    """
    Parse the command line, determine background or foreground,
    execute built-in or external commands accordingly.
    """
    global jobs, job_id_counter

    tokens = command_line.strip().split()
    if not tokens:
        return  # Empty command, ignore

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

    # Otherwise, execute external command
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
            # Parent process:
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

if __name__ == '__main__':
    shell_loop()
