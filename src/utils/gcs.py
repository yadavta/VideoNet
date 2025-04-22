import os
from typing import List, Tuple
from google.cloud import storage
from concurrent.futures import ThreadPoolExecutor
import time
import json
from pathlib import Path
from loguru import logger
from tqdm import tqdm
from google.oauth2 import service_account
import math


BUCKET_NAME_TO_SERVICE_ACCOUNT_CREDENTIALS_PATH = {
    "video_llm": os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
    "action_atlas": os.getenv("GOOGLE_APPLICATION_CREDENTIALS_ACTION_ATLAS"),
}

def get_file_extension(url: str) -> str:
    return os.path.splitext(url)[1]

def create_bucket(bucket_name, storage_class="STANDARD", location="US"):
    """Creates a new bucket."""
    storage_client = storage.Client()

    bucket = storage_client.bucket(bucket_name)
    bucket.storage_class = storage_class
    new_bucket = storage_client.create_bucket(bucket, location=location)

    logger.info(f"Bucket {new_bucket.name} created with storage class {new_bucket.storage_class} in {new_bucket.location}.")


def list_blobs(bucket_name):
    """Lists all the blobs in the bucket."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blobs = bucket.list_blobs()
     
    return blobs


def list_blobs_by_prefix(bucket_name, prefix, delimiter=None):
    """Lists all the blobs in the bucket under a specified directory (prefix)."""
    credentials_path = BUCKET_NAME_TO_SERVICE_ACCOUNT_CREDENTIALS_PATH.get(bucket_name)
    if not credentials_path:
        logger.error(f"No credentials path found for bucket {bucket_name}.")
        return []

    credentials = service_account.Credentials.from_service_account_file(credentials_path)
    storage_client = storage.Client(credentials=credentials)
    bucket = storage_client.bucket(bucket_name)
    # Note: The delimiter argument ensures that only blobs in the 'directory' are listed
    blobs = bucket.list_blobs(prefix=prefix, delimiter=delimiter)
    return blobs


def list_directories(bucket_name, prefix='', delimiter='/'):
    """
    Lists unique 'directories' in a given bucket.
    Note that directories do not have a meaning in cloud storage context
    and they are just part of the prefix of a blob path. However, still 
    in some use cases it's helpful to have a list of immediate directories
    within a blob path prefix.
    """
    storage_client = storage.Client()
    iterator = storage_client.list_blobs(bucket_name, prefix=prefix, delimiter=delimiter)
    prefixes = set()

    for page in iterator.pages:
        prefixes.update(page.prefixes)

    prefixes = [p.split(delimiter)[-2] for p in prefixes]
    
    return prefixes


def download_blob(
    bucket_name,
    source_blob_name,
    destination_file_name,
    verbose=False,
    max_retries:int=5,
    check_existence=False,
    # handle_exception=False,
    ):
    """Downloads a blob from the bucket."""
    credentials_path = BUCKET_NAME_TO_SERVICE_ACCOUNT_CREDENTIALS_PATH.get(bucket_name)
    if not credentials_path:
        logger.error(f"No credentials path found for bucket {bucket_name}.")
        return -1

    for retry in range(max_retries):
        try:
            credentials = service_account.Credentials.from_service_account_file(credentials_path)
            storage_client = storage.Client(credentials=credentials)
            # storage_client = storage.Client()
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(source_blob_name)
            if check_existence:
                if not blob.exists():
                    logger.warning(f"Blob {source_blob_name} does not exist in bucket {bucket_name}.")
                    return -1
            blob.download_to_filename(destination_file_name)
            if verbose:
                logger.info(f"Blob {source_blob_name} downloaded to {destination_file_name}.")
            return
        except Exception as e:
            if retry < max_retries - 1:
                logger.info(f"Retrying downloading blob {source_blob_name} from bucket {bucket_name}...")
                time.sleep(5)
    return -1


def download_blobs_by_prefix(
    bucket_name, 
    destination_dir, 
    prefix=None, 
    verbose=False,
    ):
    """Downloads all the blobs in the bucket that are filtered by prefix."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)

    blobs = bucket.list_blobs(prefix=prefix)  # Get blobs in the bucket

    for blob in blobs:
        if blob.name == prefix and prefix.endswith('/'):
            continue
        # Construct a full local path to save the file
        rel_path = os.path.relpath(blob.name, prefix)
        # destination_blob_path = os.path.join(destination_dir, blob.name)
        destination_blob_path = os.path.join(destination_dir, rel_path)
        # Create directories if not exist
        os.makedirs(os.path.dirname(destination_blob_path), exist_ok=True)
        # Download the blob
        blob.download_to_filename(destination_blob_path)
        if verbose:
            logger.info(f"Blob {blob.name} downloaded to {destination_blob_path}.")

 
def _upload_blobs_single_thread(
    fpath: str,
    bucket_name: str,
    destination_blob_prefix: str,
    shard_info=None,
    remove_original_file=False,
    verbose=False
):
    """
    This function should only be called by upload_blobs_multithread so
    please don't use it directly. If you want to upload files to 
    GCS, please use upload_blobs_multithread, upload_blob, or
    upload_directory_to_gcs.
    """
    if shard_info is not None:
        idx, shard_size, num_shards = shard_info
        shard_idx = (idx // shard_size) + 1
        shard_prefix = f"{str(shard_idx).zfill(5)}_of_{str(num_shards).zfill(5)}"
        destination_blob_prefix = os.path.join(destination_blob_prefix, shard_prefix)
 
    ret = upload_blob(
        bucket_name=bucket_name,
        source_file_name=str(fpath),
        destination_blob_name=os.path.join(destination_blob_prefix, fpath.name),
        verbose=verbose
    )

    if ret != -1 and remove_original_file:
        if verbose:
            logger.info(f"Removing {fpath}.")
        os.remove(fpath)


def upload_blobs_multithread(
    source_dir: str,
    bucket_name: str,
    destination_blob_prefix: str,
    max_workers=5,
    shard_size=None,
    remove_original_file=False,
    verbose=False,
    keep_hierarchy=False
):
    """
    upload all the files in the source dir with multiple threads to the bucket with the specified
    root prefix. If shard_size is specified, then the files will be sharded into 
    multiple subdirectories where each subdirectory contains at most shard_size files. 
    Note that this function does not support hierarchical directory structure.
    if keep hierarchy is True, then the directory structure will be preserved and will be uploaded as
    is to the destination bucket.
    """
    if keep_hierarchy:
        files_to_upload = sorted(list(Path(source_dir).glob("**/*")))
        files_to_upload = [fpath for fpath in files_to_upload if fpath.is_file()]
        # get the relative path of each file to the source_dir
        rel_paths = [str(fpath.relative_to(source_dir)) for fpath in files_to_upload]
        destination_blob_prefixes = [os.path.join(destination_blob_prefix, rel_path) for rel_path in rel_paths]
        assert shard_size is None, "shard_size is not supported when keep_hierarchy is True."
    else:  
        files_to_upload = sorted(list(Path(source_dir).glob("*")))

    if verbose:
        logger.info(f"Uploading {len(files_to_upload)} files to gs://{bucket_name}/{destination_blob_prefix}.")

    if shard_size is not None:
        num_shards = math.ceil(len(files_to_upload) / shard_size)
        if verbose:
            logger.info(f"Sharding {len(files_to_upload)} files into {num_shards} shards.")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        if shard_size is None:
            if keep_hierarchy:
                for i, file_path in enumerate(files_to_upload):
                    futures.append(executor.submit(
                        _upload_blobs_single_thread,
                        file_path,
                        bucket_name,
                        destination_blob_prefixes[i],
                        remove_original_file=remove_original_file,
                        verbose=True
                    ))
            else:
                for i, file_path in enumerate(files_to_upload):
                    futures.append(executor.submit(
                        _upload_blobs_single_thread,
                        file_path,
                        bucket_name,
                        destination_blob_prefix,
                        remove_original_file=remove_original_file,
                        verbose=True
                    )) 
        else:
            for i, file_path in enumerate(files_to_upload):
                futures.append(executor.submit(
                    _upload_blobs_single_thread,
                    file_path, 
                    bucket_name,
                    destination_blob_prefix,
                    (i, shard_size, num_shards),
                    remove_original_file=remove_original_file,
                    verbose=False
                ))
        for future in tqdm(futures, total=len(files_to_upload), desc="Uploading files"):
            future.result()


def _download_blobs_single_thread(
    blob_path: str,
    bucket_name: str,
    download_dir: str,
    shard_info=None,
    verbose=False
):
    """
    This function should only be called by upload_blobs_multithread so 
    please don't use it directly. If you want to upload files to 
    GCS, please use upload_blobs_multithread, upload_blob, or 
    upload_directory_to_gcs.
    """
    if shard_info is not None:
        idx, shard_size, num_shards = shard_info
        shard_idx = (idx // shard_size) + 1
        shard_prefix = f"{str(shard_idx).zfill(5)}_of_{str(num_shards).zfill(5)}"
        download_dir = os.path.join(download_dir, shard_prefix)
    os.makedirs(download_dir, exist_ok=True)
    dest_fname = os.path.join(download_dir, blob_path.split('/')[-1])
    if os.path.exists(dest_fname):
        if verbose:
            logger.info(f"File {dest_fname} already exists. Skipping download.")
    else:
        ret = download_blob(
            bucket_name=bucket_name,
            source_blob_name=str(blob_path),
            destination_file_name=dest_fname,
            verbose=verbose,
            max_retries=5
        )


def download_blobs_multi_thread(
    prefix: str,
    blobs: List[str],
    bucket_name: str,
    download_dir: str,
    max_workers=5,
    shard_size=None,
    verbose=False,
    keep_hierarchy=True
):
    """ 
    Either provide the prefix so we can list the blobs and find the
    blobs under that prefix.
    Otherwise just give a list of blobs to download. 
    """
    if prefix:
        assert blobs is None
        blobs_to_download = list_blobs_by_prefix(bucket_name, prefix)
        if keep_hierarchy:
            logger.info("Downloading blobs with keep_hierarchy=True.")
            # files_to_upload = sorted(list(Path(source_dir).glob("**/*")))
            # files_to_upload = [fpath for fpath in files_to_upload if fpath.is_file()]
            # get the relative path of each file to the source_dir
            # rel_paths = [str(fpath.relative_to(source_dir)) for fpath in files_to_upload]
            # destination_blob_prefixes = [os.path.join(destination_blob_prefix, rel_path) for rel_path in rel_paths]
            try:
                blob_paths = [blob.name for blob in blobs_to_download]
                # get the rel path of blob_path to the prefix
                rel_paths = [blob_path.split(prefix)[1] for blob_path in blob_paths]
                rel_dirs = [os.path.dirname(rel_path) for rel_path in rel_paths]
            except Exception as e:
                logger.info(f"Error: {e}")
                logger.info(f"prefix: {prefix}")
                raise e
                
            download_dirs = [os.path.join(download_dir, rel_dir) for rel_dir in rel_dirs]
            assert shard_size is None, "shard_size is not supported when keep_hierarchy is True."
    else:
        assert prefix is None
        assert blobs is not None
        blob_paths = blobs

    if verbose:
        logger.info(f"Downloading {len(blob_paths)} files to {download_dir}")

    if shard_size is not None:
        num_shards = math.ceil(len(blob_paths) / shard_size)
        if verbose:
            logger.info(f"Sharding {len(blob_paths)} files into {num_shards} shards.")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        if shard_size is None:
            if keep_hierarchy:
                for i, blob_path in enumerate(blob_paths):
                    futures.append(executor.submit(
                        _download_blobs_single_thread,
                        blob_path,
                        bucket_name,
                        download_dirs[i],
                        verbose=verbose,
                    ))
            else:
                for i, blob_path in enumerate(blob_paths):
                    futures.append(executor.submit(
                        _download_blobs_single_thread,
                        blob_path,
                        bucket_name,
                        download_dir,
                        verbose=True
                    )) 
        else:
            for i, file_path in enumerate(blob_paths):
                futures.append(executor.submit(
                    _download_blobs_single_thread,
                    blob_path,
                    bucket_name,
                    download_dir,
                    (i, shard_size, num_shards),
                    verbose=False
                ))
        for future in tqdm(futures, total=len(blob_paths), desc="Downloading blobs"):
            future.result()


def upload_blob(
    bucket_name, source_file_name, 
    destination_blob_name, max_retries=5, 
    verbose=False, remove_original_file=False
):
    """Uploads a file to the bucket."""
    credentials_path = BUCKET_NAME_TO_SERVICE_ACCOUNT_CREDENTIALS_PATH.get(bucket_name)
    if not credentials_path:
        logger.error(f"No credentials path found for bucket {bucket_name}.")
        return -1

    credentials = service_account.Credentials.from_service_account_file(credentials_path)
    storage_client = storage.Client(credentials=credentials)
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)

    for retry in range(max_retries):
        try:
            if verbose:
                logger.info(f"Uploading blob {destination_blob_name} to bucket {bucket_name}...")
            blob.upload_from_filename(source_file_name)
            if verbose:
                logger.info(f"File {source_file_name} uploaded to gs://{bucket_name}/{destination_blob_name}.")
            if remove_original_file:
                if verbose:
                    logger.info(f"Removing {source_file_name}.")
                os.remove(source_file_name)
            return
        except Exception as e: 
            if retry < max_retries - 1:
                logger.info(f"Retrying uploading blob {destination_blob_name} to bucket {bucket_name}...")
                time.sleep(5)
    return -1
 

def upload_json_to_gcs(bucket_name, destination_blob_name, data, verbose=False):
    """Uploads a JSON object to the specified GCS bucket"""
    # Initialize a client
    storage_client = storage.Client()
    # Get the bucket
    bucket = storage_client.bucket(bucket_name)
    # Initialize a blob or create one if it doesn’t exist
    blob = bucket.blob(destination_blob_name)
    
    # Convert the JSON object to a string
    json_string = json.dumps(data)
    # Upload the string to GCS
    blob.upload_from_string(json_string, content_type='application/json')
    if verbose:
        logger.info(f"File {destination_blob_name} uploaded to {bucket_name}.")
 
    
def upload_directory_to_gcs(
    bucket_name,
    directory_path, 
    destination_path, 
    verbose=False,
    remove_original_files=False
    ):
    """Uploads a directory to GCS, preserving the directory structure."""
    for dirpath, _, filenames in os.walk(directory_path):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            # Ensure the path on GCS matches the local directory structure
            blob_path = os.path.join(destination_path, os.path.relpath(file_path, directory_path))
            upload_blob(bucket_name, file_path, blob_path)
            if verbose:
                logger.info(f"File {file_path} uploaded to gs://{bucket_name}/{blob_path}.")
            if remove_original_files:
                if verbose:
                    logger.info(f"Removing {file_path}.")
                os.remove(file_path)


def delete_blob_by_prefix(bucket_name, prefix, verbose=False):
    """
    Delete all blobs with the specified prefix (folder_path) in the bucket.
    
    :param bucket_name: Name of the GCS bucket.
    :param folder_path: Prefix (i.e., "folder") to be deleted.
    """
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    
    # Note: The list_blobs method uses a flat namespace under the hood,
    # so you can think of folder_path as a prefix here.
    blobs = bucket.list_blobs(prefix=prefix)
    
    for blob in blobs:
        blob.delete()
        if verbose:
            logger.info(f"Blob {blob.name} from bucket {bucket_name} deleted.")


def delete_blob(bucket_name, blob_name):
    """Deletes a blob from the bucket."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.delete() 
    logger.info(f"Blob {blob_name} from bucket {bucket_name} deleted.")


def download_blob_as_bytes(
    bucket_name: str,
    file_name: str,
    max_retries: int = 5,
    ) -> bytes:
    """ Load a blob from bucket as bytes"""
    content = None
    for retry in range(max_retries):
        try:
            storage_client = storage.Client()
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(file_name)
            content = blob.download_as_bytes()
            return content
        except Exception as e:
            logger.warning(f"download_blob_as_bytes: Error downloading blob {file_name} from bucket {bucket_name}. Error: {e}. Returning None.")
            time.sleep(5)

    return content


def parse_gcs_url(gcs_url: str):
    """Parses a GCS URL into (bucket_name, blob_name)."""
    # Remove the 'gs://' prefix
    gcs_path = gcs_url.replace('gs://', '')

    # Split the path into (bucket_name, blob_name)
    path_parts = gcs_path.split('/', 1)

    if len(path_parts) > 1:
        # Both bucket_name and blob_name are present
        bucket_name, blob_name = path_parts
    elif len(path_parts) == 1:
        # Only bucket_name is present
        bucket_name = path_parts[0]
        blob_name = ''
    else:
        raise ValueError('Invalid GCS URL', gcs_url)

    return bucket_name, blob_name


def load_gcs_file(video_path: str, extension: str) -> bytes:
    bucket_name, blob_name = parse_gcs_url(video_path)
    return download_blob_as_bytes(bucket_name, blob_name)


def load_gcs_video(video_path: str) -> bytes:
    return load_gcs_file(video_path, extension='.mp4')


def load_gcs_gif(video_path: str) -> bytes:
    return load_gcs_file(video_path, extension='.gif')


def load_gcs_frame(video_path: str) -> bytes:
    return load_gcs_file(video_path, extension='.jpg')


def list_gcs_files(gcs_url: str) -> List[str]:
    bucket_name, blob_name = parse_gcs_url(gcs_url)
    files = list_blobs_by_prefix(bucket_name, blob_name)
    return files


if __name__ == "__main__":
    download_blobs_multi_thread(
        prefix=""
    )
    pass