# ********** modules ********** #
# chainer
import chainer
from chainer import cuda

# others
import numpy as np
import argparse
import pandas as pd
import glob, os, math
import matplotlib.pyplot as plt
import seaborn as sns
from librosa import istft, stft, load
from librosa.output import write_wav

# network named "Looking to Listen at the Cocktail Party"
from network import Audio_Visual_Net

# ********** config ********** #
SR = 16000
FFT_SIZE = 512
HOP_LEN = 160
WIN_LEN = 400
SPEC_LEN = 49
FACE_LEN = 12

# ********** utils ********** #
def LoadAudio(fname):
    y, sr = load(fname, sr=SR)
    spec = stft(y, n_fft=FFT_SIZE, hop_length=HOP_LEN, win_length=WIN_LEN)
    mag = np.abs(spec)
    mag /= np.max(mag)
    phase = np.exp(1.j*np.angle(spec))
    return mag, phase

# ********** main ********** #
def main():
    # ===== Arguments ===== #
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpu", "-g", type=int, default=-1,
                        help="specify GPU")
    parser.add_argument("--model_path", "-m", type=str,
                        default="result/model-0612-0.npz")
    parser.add_argument("--data_visual", type=str,
                        default="/mnt/d/datasets/Looking-to-Listen_small/small_visual/")
    parser.add_argument("--data_speech", type=str,
                        default="/mnt/d/datasets/Looking-to-Listen_small/small_spectrogram/")
    args = parser.parse_args()
    
    # ===== GPU or CPU ===== #
    if args.gpu >= 0:
        xp = cuda.cupy
        cuda.get_device(args.gpu).use()
    else:
        xp = np

    # ===== Load model ===== #
    print("loading model...")
    model = Audio_Visual_Net(spec_len=SPEC_LEN)
    if args.gpu >= 0:
        model.to_gpu(args.gpu)
    chainer.serializers.load_npz(args.model_path, model)   
    
    # ===== Load test data ===== #
    print("loading test data...")
    spec_input = sorted(glob.glob(os.path.join(args.data_speech, "*.npz")))
    vis_input = sorted(glob.glob(os.path.join(args.data_visual, "*")))
    assert len(spec_input)==len(vis_input), "# of files are different between faces and audios."
    l_input = len(spec_input)
    test = []
    
    for i in range(l_input):
        _num = int(os.path.basename(spec_input[i]).split(".")[0])
        _spec_input_mix, _phase = LoadAudio(fname="/mnt/d/datasets/Looking-to-Listen_small/small_mixed_wavs/{}.wav".format(_num))
        _mag = _spec_input_mix.T[np.newaxis,:,:]
        _phase = _phase.T[np.newaxis,:,:]
        _vis_input1 = xp.array(pd.read_csv(os.path.join(vis_input[0], "speech1.csv"), header=None)).astype(xp.float32) / 255.
        _vis_input2 = xp.array(pd.read_csv(os.path.join(vis_input[0], "speech2.csv"), header=None)).astype(xp.float32) / 255.
        _vis_input1 = _vis_input1.T[:,:,np.newaxis]
        _vis_input2 = _vis_input2.T[:,:,np.newaxis]
        test.append((_mag, _vis_input1, _vis_input2, _phase))
    
    # ===== Separate mixed speeches ===== #
    print("start saparating...")
    for i in range(l_input):
        print("{}/{}".format(i+1, l_input))
        loop = int(math.ceil(test[i][0].shape[1] // SPEC_LEN))
        speech1 = []
        speech2 = []
        phase = xp.array(test[i][3][0,:,:].T)
        for l in range(loop):
            # we have to reshape test data because we must add batch size dimension
            y = model.separateSpectrogram(spec=test[i][0][np.newaxis,:,(SPEC_LEN*l):(SPEC_LEN*(l+1)),:],
                                          face1=test[i][1][np.newaxis,:,(FACE_LEN*l):(FACE_LEN*(l+1)),:],
                                          face2=test[i][2][np.newaxis,:,(FACE_LEN*l):(FACE_LEN*(l+1)),:])
            y = y.data
            mask1 = xp.array(y[0,:,:257].T)
            mask2 = xp.array(y[0,:,257:].T)
            _phase = phase[:,(SPEC_LEN*l):(SPEC_LEN*(l+1))]
            d1 = chainer.cuda.to_cpu(mask1*_phase)
            d2 = chainer.cuda.to_cpu(mask2*_phase)
            speech1.append(istft(d1, hop_length=HOP_LEN, win_length=FFT_SIZE))
            speech2.append(istft(d2, hop_length=HOP_LEN, win_length=FFT_SIZE))
        speech1 = np.concatenate(speech1)
        speech2 = np.concatenate(speech2)
        write_wav(path="result-audio/{}-speech1.wav".format(i), y=speech1, sr=SR, norm=True)
        write_wav(path="result-audio/{}-speech2.wav".format(i), y=speech2, sr=SR, norm=True)
        
    print("done!!")

if __name__ == "__main__":
    main()
    