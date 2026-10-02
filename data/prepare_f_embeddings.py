#!/usr/bin/env python3
"""Optional authoring tool; never invoked by reset, startup, or data/rebuild.py.

Requires numpy, tokenizers and onnxruntime in the authoring Python environment.
Downloads only the official small model/tokenizer to the explicitly supplied
scratch directory. The model and dependencies are not included in the lab image.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer
from f_semantic import MODEL_ID, QUERY_TEXTS, raw_documents


def checksum(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def download(url, target):
    if target.exists():
        return
    temporary = target.with_suffix(target.suffix + '.part')
    with urlopen(url, timeout=180) as source, temporary.open('wb') as dest:
        size = 0
        for block in iter(lambda: source.read(1024 * 1024), b''):
            size += len(block)
            if size > 120_000_000:
                raise RuntimeError('Unexpected model download size')
            dest.write(block)
    temporary.replace(target)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model-dir', type=Path, required=True)
    parser.add_argument('--revision', help='Exact Hugging Face commit; defaults to resolving main once')
    parser.add_argument('--output', type=Path, default=Path(__file__).with_name('f_semantic_embeddings.json'))
    args = parser.parse_args()
    args.model_dir.mkdir(parents=True, exist_ok=True)
    revision = args.revision
    if not revision:
        with urlopen(f'https://huggingface.co/api/models/{MODEL_ID}', timeout=30) as response:
            revision = json.load(response)['sha']
    model_dir = args.model_dir / revision
    model_dir.mkdir(parents=True, exist_ok=True)
    model = model_dir / 'model.onnx'
    tokenizer_file = model_dir / 'tokenizer.json'
    base = f'https://huggingface.co/{MODEL_ID}/resolve/{revision}'
    download(base + '/onnx/model.onnx?download=true', model)
    download(base + '/tokenizer.json?download=true', tokenizer_file)
    tokenizer = Tokenizer.from_file(str(tokenizer_file))
    tokenizer.enable_truncation(max_length=256)
    tokenizer.enable_padding()
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(model), sess_options=options, providers=['CPUExecutionProvider'])
    documents = raw_documents()
    query_names = list(QUERY_TEXTS)
    texts = [d['_source']['title'] + '. ' + d['_source']['content'] for d in documents]
    texts += [QUERY_TEXTS[name] for name in query_names]
    encoded = tokenizer.encode_batch(texts)
    inputs = {'input_ids': np.array([e.ids for e in encoded], dtype=np.int64),
              'attention_mask': np.array([e.attention_mask for e in encoded], dtype=np.int64),
              'token_type_ids': np.array([e.type_ids for e in encoded], dtype=np.int64)}
    tokens = session.run(None, {i.name: inputs[i.name] for i in session.get_inputs()})[0]
    mask = inputs['attention_mask'][..., None].astype(np.float32)
    pooled = (tokens * mask).sum(axis=1) / np.maximum(mask.sum(axis=1), 1e-9)
    normalized = pooled / np.linalg.norm(pooled, axis=1, keepdims=True)
    vectors = [[round(float(value), 8) for value in vector] for vector in normalized]
    if normalized.shape != (len(texts), 384):
        raise RuntimeError('Unexpected encoder output shape ' + str(normalized.shape))
    for document, vector in zip(documents, vectors):
        document['_source']['embedding'] = vector
    data = {'provenance': {
        'model_id': MODEL_ID, 'revision': revision, 'license': 'Apache-2.0', 'dimensions': 384,
        'model_url': f'https://huggingface.co/{MODEL_ID}/tree/{revision}',
        'artifact': 'onnx/model.onnx', 'artifact_sha256': checksum(model),
        'tokenizer_sha256': checksum(tokenizer_file),
        'pooling': 'attention-mask mean pooling, then L2 normalization',
        'max_tokens': 256, 'document_input': 'title + ". " + content',
        'float_serialization': '8 decimal places', 'execution_provider': 'CPUExecutionProvider',
        'onnxruntime_version': ort.__version__,
        'corpus_provenance': '32 author-written synthetic guidance passages; no copied documents or customer data',
        'reproduction': 'python data/prepare_f_embeddings.py --model-dir <scratch> --revision ' + revision,
    }, 'documents': documents, 'queries': {
        name: {'text': QUERY_TEXTS[name], 'embedding': vectors[len(documents) + i]}
        for i, name in enumerate(query_names)}}
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'model_id': MODEL_ID, 'revision': revision, 'documents': len(documents),
                      'queries': len(query_names), 'dimensions': 384, 'output_bytes': args.output.stat().st_size}))


if __name__ == '__main__':
    main()
