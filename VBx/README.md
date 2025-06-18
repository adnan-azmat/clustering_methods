# VBx – Quick-start diarisation demo
Lightweight instructions for running the **VBx** speaker-diarisation pipeline that sits in this folder.

---

## 1. Create a conda env

```bash
# ① create + activate fresh python 3.8 env
conda create -n vbx python=3.8 -y
conda activate vbx
````

### 1.1  Install packages


```bash
pip install -r requirements.txt
```

---

## 3. One-line run

**Input / output layout**

`predict.py` expects a directory structure like this:

 ```
 <YOUR_IN_WAV_DIR>
 └── wav            # every *.wav to diarise goes here
     ├── talk1.wav
     ├── talk2.wav
     └── …
 ```

`YOUR_IN_WAV_DIR` should have the wav folder full of .wav files.

When you run.

> ```bash
> python predict.py --in-wav-dir <YOUR_IN_WAV_DIR> --hf-token "hf_xxx"
> ```

the script will create, **inside that same folder**

* `rttm/`  – final diarisation results, one `<wav-name>.rttm` per input WAV

```
<YOUR_IN_WAV_DIR>
└── wav            # every *.wav to diarise goes here
    ├── talk1.wav
    ├── talk2.wav
    └── …
└── rttm            # output *.rttm is shown here
    ├── talk1.rttm
    ├── talk2.rttm
    └── …
```

The script will:

1. Run a PyAnnote VAD pass and save `exp/<file>.lab`.
2. Extract x-vectors with the 16 kHz ResNet and dump them to `exp/<file>.ark`.
3. Cluster them via **AHC + VB-HMM** and write final RTTM files to `example/rttm/`.

---
