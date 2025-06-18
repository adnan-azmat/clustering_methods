To run WeSpeaker Clustering on AliMeeting the run.sh script is quite simple.

Simply ensure the path is correct below:

```
data_path=/Users/adnanazmat/Downloads/Eval_Ali
eval_path=${data_path}/Eval_Ali_far
audio_dir=${eval_path}/audio_dir
textgrid_dir=${eval_path}/textgrid_dir
```


Then run:

I think VBx environment can be used for wespeaker clustering as well.
Pls install any additional dependencies if anything is missing.

`chmod +x run.sh`

`./run.sh`