stage=2
stop_stage=6

data_path=/Users/adnanazmat/Downloads/Eval_Ali
eval_path=${data_path}/Eval_Ali_far
audio_dir=${eval_path}/audio_dir
textgrid_dir=${eval_path}/textgrid_dir

if [ ${stage} -le 2 ] && [ ${stop_stage} -ge 2 ]; then
    min_duration=0.255
    echo "[2] VAD"
    python modules/vad.py \
            --repo-path external_tools/silero-vad-3.1 \
            --scp exp/predict/wav.scp \
            --threshold 0.2 \
            --min-duration $min_duration > exp/predict/vad
fi


if [ ${stage} -le 3 ] && [ ${stop_stage} -ge 3 ]; then
    echo "[3] Extract and cluster"
    python modules/cluster.py \
            --scp exp/predict/wav.scp \
            --segments exp/predict/vad \
            --source pretrained_models/ecapa-tdnn.model \
            --output exp/predict/vad_labels
fi


if [ ${stage} -le 4 ] && [ ${stop_stage} -ge 4 ]; then
    echo "[4] Get RTTM"
    python modules/make_rttm.py \
            --labels exp/predict/vad_labels \
            --channel 1 > exp/predict/res_rttm
fi

if [ $stage -le 5 ] && [ ${stop_stage} -ge 5 ]; then
    echo "[5] Get labels"
    mkdir -p exp/tmp
    mkdir -p exp/label
    find ${audio_dir} -name "*\.wav" > exp/tmp/tmp
    sort  exp/tmp/tmp > exp/tmp/wavlist
    awk -F '/' '{print $NF}'  exp/tmp/wavlist | awk -F '.' '{print $1}' >  exp/tmp/uttid
    find -L $textgrid_dir -iname "*.TextGrid" >  exp/tmp/tmp
    sort  exp/tmp/tmp  > exp/tmp/textgrid.flist
    paste exp/tmp/uttid exp/tmp/textgrid.flist > exp/tmp/uttid_textgrid.flist
    while read text_file
    do
        text_grid=`echo $text_file | awk '{print $1}'`
        text_grid_path=`echo $text_file | awk '{print $2}'`
        python external_tools/make_textgrid_rttm.py --input_textgrid_file $text_grid_path \
                                        --uttid $text_grid \
                                        --output_rttm_file exp/label/${text_grid}.rttm
    done < exp/tmp/uttid_textgrid.flist
    rm -r exp/tmp
    cat exp/label/*.rttm > exp/label/all.rttm
fi


if [ ${stage} -le 6 ] && [ ${stop_stage} -ge 6 ]; then    
    echo "[6] Get DER result"
    perl external_tools/SCTK-2.4.12/src/md-eval/md-eval.pl -c 0.25 -r exp/label/all.rttm -s exp/predict/res_rttm 
fi
