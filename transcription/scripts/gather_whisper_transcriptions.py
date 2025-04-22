from datasets import Dataset, Value

def reorder_segments(example):
    example["segments"] = [
        {
            "id":    seg.get("id", idx),
            "start": seg["start"],
            "end":   seg["end"],
            "text":  seg["text"],
        }
        for idx, seg in enumerate(example["segments"])
    ]
    return example

segments_feature = [{
    "id":    Value("int64"),
    "start": Value("float64"),
    "end":   Value("float64"),
    "text":  Value("string"),
}]

    
if __name__ == '__main__':
    # Load the dataset
    prefix = 'transcription/output/batch2_362k/*.jsonl'
    dataset = Dataset.from_json([prefix])
    dataset = dataset.map(reorder_segments, load_from_cache_file=False)
    dataset = dataset.cast_column("segments", segments_feature)
    
    # Save the dataset to a new parquet file
    dataset.to_parquet("transcription/batch2_362k.parquet")


    