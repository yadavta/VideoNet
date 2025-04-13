import multiprocessing as mp
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List, Literal
import json

import time
from tqdm import tqdm


class BatchCaller:

    @classmethod
    def call_batch(cls, fn: Callable, data: List, **kwargs) -> List:
        """
        Calls a function on a batch of data.

        Args:
            fn (Callable): The function to call.
            data (List): The data to process.

        Returns:
            List: The results of the function calls.
        """
        return [fn(d) for d in tqdm(data)]
    
    @classmethod
    def batch_process_save(cls, 
                           data: List, 
                           fn: Callable, 
                           output_file: str, 
                           batch_size=1000, 
                           sort_key: str=None, 
                           write_mode:Literal['a','w']='a',
                           max_workers=None,
                           **kwargs):
        """
        Processes data in batches and saves the results to a file.

        Args:
            data (List): The list of data to process.
            fn (Callable): The function to call on each batch.
            output_file (str): The file to save the results to.
            batch_size (int, optional): The size of each batch. Defaults to 1000.
            sort_key (str, optional): The key to sort the results by. If None, no sorting is done. Defaults to None.
            write_mode (Literal['a','w'], optional): The mode to open the file in. 'a' for append and 'w' for write. Defaults to 'a'.

        Returns:
            List: The results of the function calls.
        """
        all_result: List = []
        for idx in tqdm(range(0, len(data), batch_size)):
            
            # Process in batches
            batch_result: list = cls.call_batch(fn, data[idx:idx+batch_size], **kwargs)
            batch_result = [r for r in batch_result if r is not None]

            # Sort if a key is provided
            if sort_key is not None:
                batch_result = sorted(
                    batch_result,
                    key=lambda x: x[sort_key]
                )
            m = 'a' if write_mode == 'a' or idx > 0 else 'w'
            with open(output_file, m) as f:
                # Save batch results to file
                for r in batch_result:
                    f.write(json.dumps(r) + '\n')
                print(f'Save {len(batch_result)} batch data to {output_file}')

            all_result += batch_result
        
        return all_result
    
    @staticmethod
    def _retry_wrapper(fn, datum, retry_delay, max_retries):
        retries = 0
        while retries < max_retries:
            try:
                return fn(datum)
            except Exception as e:
                print(f"Error: {e} on datum: {datum}. Retrying {retries+1}/{max_retries}...")
                time.sleep(retry_delay)
                retries += 1
        print(f"Failed after {max_retries} retries for datum: {datum}")
        return None


class FutureThreadCaller(BatchCaller):
    """
    Uses concurrent.futures.ThreadPoolExecutor to call a function on a dataset concurrently.
    Updates a tqdm progress bar as each future completes.
    """
    @classmethod
    def call_batch(cls, fn, data, max_workers=None, retry_delay=3, max_retries=3):
        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all the tasks
            future_to_data = {executor.submit(cls._retry_wrapper, fn, d, retry_delay, max_retries): d for d in data}

            for future in tqdm(as_completed(future_to_data), total=len(future_to_data), 
                               desc="Processing (Threads)"):
                try:
                    res = future.result()
                    if res is not None:
                        results.append(res)
                except Exception as e:
                    print("Error processing data:", e)
        return results

class MultiProcessCaller(BatchCaller):
    """
    Uses native multiprocessing instead of concurrent.futures to support tqdm progress bar
    """
    @classmethod
    def call_batch(cls, fn, data, max_workers=None, retry_delay=3, max_retries=3):
        results = []
        with mp.Pool(processes=max_workers) as pool:
            # Use tqdm to wrap the iterable
            for res in tqdm(pool.imap_unordered(cls._retry_wrapper, [(fn, d, retry_delay, max_retries) for d in data]), 
                            total=len(data), desc="Processing (Processes)"):
                if res is not None:
                    results.append(res)
        return results