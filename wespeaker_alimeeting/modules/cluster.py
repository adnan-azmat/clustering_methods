# Copyright (c) 2022 Xu Xiang
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import argparse, warnings
from collections import OrderedDict
import concurrent.futures as cf

import numpy as np, random

import scipy.linalg
from tqdm import tqdm

from sklearn.cluster._kmeans import k_means

import torch
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

import torchaudio

from speaker_encoder import ECAPA_TDNN

warnings.simplefilter("ignore")

def get_args():
	parser = argparse.ArgumentParser(description='')
	parser.add_argument('--scp', required=True, help='wav scp')
	parser.add_argument('--segments', required=True, help='vad segments')
	parser.add_argument('--output', required=True, help='output label file')
	parser.add_argument('--source', required=True, help='onnx model')
	parser.add_argument('--batch-size', type=int, default=96, help='batch size for embedding extraction')
	args = parser.parse_args()

	return args


def compute_embeddings(scp, segments, source, 
					   batch_size, sampling_rate=16000,
					   window_secs=1.50, period_secs=0.75, frame_shift=10):

	def read_segments(segments):
		utt_to_segments = OrderedDict()
		for line in open(segments, 'r'):
			seg, utt, begin, end = line.strip().split()
			begin, end = float(begin), float(end)
			if utt not in utt_to_segments:
				utt_to_segments[utt] = [(seg, begin, end)]
			else:
				utt_to_segments[utt].append((seg, begin, end))

		return utt_to_segments

	def read_scp(scp):
		utt_to_wav = OrderedDict()
		for line in open(scp, 'r'):
			utt, wav = line.strip().split()
			utt_to_wav[utt] = wav

		return utt_to_wav

	def repeat_to_fill(x, window_fs):
		assert len(x.size()) == 2
		assert x.size(1) == 1
		length = x.size(0)
		num = (window_fs + length - 1) // length

		return x.repeat(num, 1)[:window_fs, :]

	def subsegment(wav, segments, window_fs, period_fs):
		subsegs = []
		subseg_signals = []

		signal, fs = torchaudio.load(wav, channels_first=False)
		signal = signal[:,0].unsqueeze(1)
		assert len(signal.size()) == 2
		assert sampling_rate == fs

		for (seg, begin, end) in segments:
			seg_begin = int(begin * sampling_rate)
			seg_end = int(end * sampling_rate)
			seg_signal = signal[seg_begin: seg_end + 1, :]
			seg_length = seg_end - seg_begin

			if seg_length <= window_fs:
				subseg = seg + "-{:08d}-{:08d}".format(
					0,
					int(seg_length / sampling_rate * 1000 // frame_shift))
				subseg_signal = repeat_to_fill(seg_signal, window_fs)

				subsegs.append(subseg)
				subseg_signals.append(subseg_signal)
			else:
				max_subseg_begin = seg_length - window_fs + period_fs
				for subseg_begin in range(0, max_subseg_begin, period_fs):
					subseg_end = min(subseg_begin + window_fs, seg_length)
					subseg = seg + "-{:08d}-{:08d}".format(
						int(subseg_begin / sampling_rate * 1000 / frame_shift),
						int(subseg_end / sampling_rate * 1000 / frame_shift))
					subseg_signal = repeat_to_fill(
						seg_signal[subseg_begin: subseg_end + 1, :], window_fs)

					subsegs.append(subseg)
					subseg_signals.append(subseg_signal)
		return subsegs, subseg_signals

	def init_speaker_encoder(source):
		speaker_encoder = ECAPA_TDNN(C=1024).to(DEVICE)
		speaker_encoder.eval()
		loadedState = torch.load(source, map_location=DEVICE)
		selfState = speaker_encoder.state_dict()
		for name, param in loadedState.items():
			if name in selfState:
				selfState[name].copy_(param)
		for param in speaker_encoder.parameters():
			param.requires_grad = False 
		return speaker_encoder

	def extract_embeddings(wavs, batch_size, model):
		embeddings = []
		for i in range(0, wavs.size(0), batch_size):
			batch_wavs = wavs[i: i + batch_size, :]
			with torch.no_grad():
				batch_embs = model.forward(batch_wavs.to(DEVICE))
			batch_embs = batch_embs.cpu().numpy()
			embeddings.append(batch_embs)
		embeddings = np.vstack(embeddings)

		return embeddings

	window_fs = int(window_secs * sampling_rate)
	period_fs = int(period_secs * sampling_rate)

	subsegs_list = []
	embeddings_list = []

	utt_to_wav = read_scp(scp)
	utt_to_segments = read_segments(segments)

	model = init_speaker_encoder(source)
	room_id_dic = {'R8009_M8018_MS809': 2, 'R8009_M8019_MS810': 2, 'R8008_M8013_MS807': 3, 'R8009_M8020_MS810': 2, \
					'R8007_M8010_MS803': 4, 'R8007_M8011_MS806': 4, 'R8003_M8001_MS801': 4, 'R8001_M8004_MS801': 4}
	num_speaker_list = []
	for utt in tqdm(utt_to_wav.keys()):
		# Per utterance processing
		wav = utt_to_wav[utt]
		num_speaker_list.append(room_id_dic[utt])
		if utt not in utt_to_segments:
			continue
		segments = utt_to_segments[utt]

		# Extract wav data using sliding window with overlap for each utterance
		utt_subsegs, utt_subseg_signals = subsegment(wav, segments,
													 window_fs, period_fs)
		# Convert a list of Tensor to a Tensor
		utt_subseg_signals = torch.stack(utt_subseg_signals).squeeze(-1)

		# Extract embeddings for each subsegment-level wav data
		utt_embeddings = extract_embeddings(utt_subseg_signals, batch_size, model)
		# Collect embeddings for each utterance
		subsegs_list.append(utt_subsegs)
		embeddings_list.append(utt_embeddings)

	return subsegs_list, embeddings_list, num_speaker_list


def cluster(embeddings, num_spks, p=.01, min_num_spks=2, max_num_spks=4):
	# Define utility functions
	def cosine_similarity(M):
		M = M / np.linalg.norm(M, axis=1, keepdims=True)
		return 0.5 * (1.0 + np.dot(M, M.T))

	def prune(M, p):
		m = M.shape[0]
		if m < 1000:
			n = max(m - 10, 2)
		else:
			n = int((1.0 - p) * m)
		for i in range(m):
			indexes = np.argsort(M[i, :])
			low_indexes, high_indexes = indexes[0:n], indexes[n:m]
			M[i, low_indexes] = 0.0
			M[i, high_indexes] = 1.0
		return 0.5 * (M + M.T)

	def laplacian(M):
		M[np.diag_indices(M.shape[0])] = 0.0
		D = np.diag(np.sum(np.abs(M), axis=1))
		return D - M

	def spectral(M, num_spks, min_num_spks, max_num_spks):
		eig_values, eig_vectors = scipy.linalg.eigh(M)
		num_spks = num_spks if num_spks is not None \
			else np.argmax(np.diff(eig_values[:max_num_spks + 1])) + 1
		num_spks = max(num_spks, min_num_spks)
		return eig_vectors[:, :num_spks]

	def kmeans(data):
		k = data.shape[1]
		_, labels, _ = k_means(data, k, random_state=None, n_init=10)
		return labels

	# Fallback for trivial cases
	if len(embeddings) <= 2:
		return [0] * len(embeddings)

	# Compute similarity matrix	
	similarity_matrix = cosine_similarity(np.array(embeddings))
	# Prune matrix with p interval
	pruned_similarity_matrix = prune(similarity_matrix, p)
	# Compute Laplacian
	laplacian_matrix = laplacian(pruned_similarity_matrix)
	# Compute spectral embeddings
	spectral_embeddings = spectral(laplacian_matrix, num_spks,
								   min_num_spks, max_num_spks)
	# Assign class labels
	labels = kmeans(spectral_embeddings)
	return labels


def main():
	args = get_args()

	subsegs_list, embeddings_list, num_speaker_list = compute_embeddings(args.scp,
													   args.segments,
													   args.source,
													   args.batch_size)
	with cf.ProcessPoolExecutor() as executor, open(args.output, 'w') as f:
		for (subsegs, labels) in zip(subsegs_list,
									 executor.map(cluster, embeddings_list, num_speaker_list)):
			[print(subseg, label, file=f) for (subseg, label) in zip(subsegs, labels)]


if __name__ == '__main__':
	torch.set_num_threads(1)
	np.random.seed(1)
	random.seed(1)

	main()
