"""
#Instructions for compiling and running it

#Pre requisites
1. Python 3 must be installed
2. Program file (word_frequency.py) and sample text file (sample.txt) should be in the same directory.
3. Execute below command to run the program based on python version. 3 is the number of threads to divide the file into
   python word_frequency.py sample.txt 3
   or
   python3 word_frequency.py sample.txt 3
"""


import threading
from collections import Counter
import sys

# Define a custom thread class for processing a segment of the text
class WordFrequencyThread(threading.Thread):
    def __init__(self, text_segment, index, results):
        threading.Thread.__init__(self)
        self.text_segment = text_segment  # Segment of text this thread will process
        self.index = index  # Index to place result in shared list
        self.results = results  # Shared list to store intermediate results

    # The code that runs when the thread starts
    def run(self):
        # Split the text into words, clean punctuation, and convert to lowercase
        words = [word.strip('.,!?;:"()[]{}').lower() for word in self.text_segment.split()]
        # Count word frequencies in this segment
        freq = Counter(words)
        # Store the result in the shared results list
        self.results[self.index] = freq
        # Print intermediate result
        print(f"\n[Thread {self.index + 1}] Intermediate Word Frequencies:\n{freq}")


# Function to split the text into N segments based on lines
def split_text(text, num_segments):
    lines = text.splitlines()  # Split the entire text into lines
    avg_lines = len(lines) // num_segments  # Approximate number of lines per segment
    segments = []
    for i in range(num_segments):
        start = i * avg_lines
        # Ensure the last segment gets the remaining lines
        end = (i + 1) * avg_lines if i < num_segments - 1 else len(lines)
        # Join lines back into a string for this segment
        segments.append('\n'.join(lines[start:end]))
    return segments


# Function to combine all intermediate results into a final count
def consolidate_frequencies(thread_results):
    total_freq = Counter()
    for freq in thread_results:
        total_freq.update(freq)  # Merge counters
    return total_freq


# Main function to control program flow
def main():
    if len(sys.argv) != 3:
        print("Usage: python word_frequency.py <filename> <number_of_segments>")
        sys.exit(1)

    filename = sys.argv[1]
    num_segments = int(sys.argv[2])

    # Try to open the file and read the content
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            text = file.read()
    except FileNotFoundError:
        print("Error: File not found.")
        sys.exit(1)

    # Split text into segments
    segments = split_text(text, num_segments)

    # Prepare shared list for thread results
    thread_results = [None] * num_segments
    threads = []

    # Create and start a thread for each segment
    for i in range(num_segments):
        thread = WordFrequencyThread(segments[i], i, thread_results)
        thread.start()
        threads.append(thread)

    # Wait for all threads to finish
    for thread in threads:
        thread.join()

    # Consolidate final results from all threads
    final_result = consolidate_frequencies(thread_results)

    # Print the final word frequency result
    print("\n✅ Final Consolidated Word Frequencies:\n")
    for word, count in final_result.most_common():
        print(f"{word}: {count}")


# Entry point of the script
if __name__ == "__main__":
    main()

