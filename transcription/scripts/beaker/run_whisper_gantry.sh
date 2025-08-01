WORKSPACE=ai2/sg-train # Use your own workspace
BEAKER_IMAGE='jamesp/videonet-whisper-transcription-cu_11.8_pytorch_2.5.1_transformers_4.49.0.dev0_flash-attn_2.6.3_vllm_0.7.3_awq'
BEAKER_IMAGE='jamesp/videonet-whisperx-cache-transcription-cu_11.8_pytorch_2.5.1_transformers_4.49.0.dev0_flash-attn_2.6.3_vllm_0.7.3_awq'
NUM_GPUS_PER_EVAL=1
OUTPUT_DIR=/results


# Included as reference to create beaker image
install_dependencies() {
    echo "Installing dependencies..."
    pip install -e .[transcription]
    conda install conda-forge::ffmpeg
    pip install google-generativeai
    pip install grpcio==1.67.1 grpcio-status==1.67.1
    pip install ctranslate2==3.24.0
}

CLUSTERS=(
    ai2/augusta-google-1
    ai2/jupiter-cirrascale-2
    ai2/ceres-cirrascale
    ai2/neptune-cirrascale
    ai2/saturn-cirrascale
)

# Set CLUSTER specific variables
CLUSTER_SETTINGS=""
for cluster in "${CLUSTERS[@]}"; do
    CLUSTER_SETTINGS+="--cluster $cluster "
done

set -x
### Set the following variables ###
# FNAME='oe-training-yt-crawl-video-list-04-10-2025.jsonl'
# DATA_NAME='yt-crawl-04-10-2025'

# FNAME='oe-training-yt-crawl-video-list-04-10-2025-with-lang-to-process.jsonl'
# DATA_NAME='yt-crawl-04-10-2025-with-lang-to-process'

FNAME=batch2_362k.jsonl
DATA_NAME='yt-crawl-batch2_362k'


SHARD_START=0
SHARD_END=63 # inclusive
NUM_SHARDS=${NUM_SHARDS:-64}
WHISPER_MODE='whisperx' # [whisper-gpu whisperx]
WHISPER_MODEL=large-v3-turbo
WHISPER_CACHE_DIR=/cache/whisper
BATCH_SIZE=100
#########
PRIORITY=normal
NUM_JOBS=$((SHARD_END - SHARD_START + 1)) # don't change this

TASK=run_whisper
TASK_NAME=${TASK}_${DATA_NAME}_${NUM_SHARDS}_${SHARD_START}_${SHARD_END}
BEAKER_NAME=$(echo ${TASK_NAME} | cut -c 1-123) # don't change this: avoids max length limit when identifiers are added for duplicate names
gantry run \
    --yes \
    --allow-dirty \
    --name $BEAKER_NAME \
    --task-name $TASK_NAME \
    --workspace $WORKSPACE \
    --description "run_whisper_gantry.sh; DATA: ${DATA_NAME}; \
                   NUM_SHARDS: $NUM_SHARDS; SHARD_IDX: [$SHARD_START, $SHARD_END];" \
    --beaker-image $BEAKER_IMAGE \
    --env-secret OPENAI_API_KEY=OPENAI_API_KEY \
    --env-secret GOOGLE_APPLICATION_CREDENTIALS_JSON=GOOGLE_APPLICATION_CREDENTIALS_JSON \
    --env-secret GOOGLE_APPLICATION_CREDENTIALS=GOOGLE_APPLICATION_CREDENTIALS \
    --env-secret SERVICE_ACCOUNT=SERVICE_ACCOUNT \
    --env GOOGLE_CLOUD_PROJECT=oe-training \
    --env CLOUDSDK_CORE_PROJECT=oe-training \
    --env WHISPER_CACHE_DIR=$WHISPER_CACHE_DIR \
    --env GPUS=$NUM_GPUS_PER_EVAL \
    $CLUSTER_SETTINGS \
    $MOUNT_SETTINGS \
    --priority $PRIORITY \
    --preemptible \
    --gpus $NUM_GPUS_PER_EVAL \
    --venv 'base' \
    --budget "ai2/oe-training" \
    --replicas $NUM_JOBS \
    --install 'pip install -e .[transcription]; pip install ctranslate2==3.24.0' \
    -- /bin/bash -c "
    {
    export SHARD_IDX=\$((\$BEAKER_REPLICA_RANK + $SHARD_START))
    echo \"SHARD_IDX: \$SHARD_IDX\"

    gcloud auth activate-service-account \$SERVICE_ACCOUNT --key-file=/root/service-account.json
    $GCS_COMMANDS
    echo "\$GOOGLE_APPLICATION_CREDENTIALS_JSON" > \$GOOGLE_APPLICATION_CREDENTIALS

    set -x

    gsutil cp gs://oe-training-yt-crawl/batches-to-be-transcribed/${FNAME} ./
    python -m transcription.scripts.run_whisper_batch \
        --mode $WHISPER_MODE \
        --whisper_model $WHISPER_MODEL \
        --input_file $FNAME \
        --num_shards $NUM_SHARDS \
        --shard_index \$SHARD_IDX \
        --batch_size $BATCH_SIZE \
        --output_dir ${OUTPUT_DIR} \
        --all_lang \
        $FLAGS
    sudo chmod -R 777 ${OUTPUT_DIR}
    }
    "