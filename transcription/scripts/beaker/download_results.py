import os
from beaker import Beaker, Job, Dataset
import argparse
from collections import defaultdict

def fetch_latest_jobs(jobs: tuple[Job], 
                       only_completed: bool = False
) -> list[Job]:
    """
    Gather the latest jobs from a tuple of jobs.
    """

    def valid_job(job: Job) -> bool:
        """
        Check if the job is valid.
        """
        if only_completed:
            return job.status.exited and not job.status.canceled
        return job.status.started

    job_timestamps = defaultdict(list)
    for job in jobs:
        if valid_job(job):
            job_timestamps[job.name].append({
                'job': job,
                'started': job.status.started,
            })
        elif not job.status.canceled:
            print(job.name)

    # Sort the jobs by timestamp
    latest_jobs = []
    for name, val in job_timestamps.items():
        val.sort(key=lambda x: x['started'], reverse=True)
        latest_jobs.append(val[0]['job'])

    return latest_jobs

def download_results(job: Job, 
                     output_dir: str
) -> None:
    """
    Download the results of a job.
    """

    # Print the job name and status
    dataset_id = job.result.beaker
    print(f"Downloaded results for job: {job.name} (dataset: {dataset_id}) to {output_dir}")

    # Download the results
    output_dir = os.path.join(output_dir, job.name)
    os.makedirs(output_dir, exist_ok=True)
    beaker.dataset.fetch(dataset_id, target=output_dir, force=True)


if __name__ == "__main__":

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Download results from Beaker experiment.")
    parser.add_argument('exp_name', type=str, help='Name of the Beaker experiment to download results from.')
    parser.add_argument('--output_dir', type=str, required=True, help='Directory to save the downloaded results.')
    parser.add_argument('--completed', action='store_true', help='Only download completed jobs.')

    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # Set up Beaker client
    beaker = Beaker.from_env()

    # exp_name = 'jamesp/run_whisper_yt-crawl-04-10-2025_256_129_255'
    exp = beaker.experiment.get(args.exp_name)

    # Get the latest jobs
    latest_jobs = fetch_latest_jobs(exp.jobs, only_completed=args.completed)
    print(f"Found {len(latest_jobs)} jobs in experiment: '{args.exp_name}'")

    for job in latest_jobs:
        download_results(job, args.output_dir)

