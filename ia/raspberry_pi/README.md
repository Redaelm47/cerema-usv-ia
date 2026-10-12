# Raspberry Pi 4

- [ ] Monter 2 caméras (si possible) sur le Raspberry Pi 4
- [ ] Porter la chaîne de détection de manière pérenne sur le Raspberry Pi


Pour lancer sur la raspberry pi : 
```
python ia/raspberry_pi/run_program_on_pi.py --script yolo_json_export.py --model yolo11n.pt --thresh 0.6 --interval 2.0
```

```
python raspberry-pi/run_program_on_pi.py --script yolo_detect_rasp.py --model best.pt 
```

```
scp pi@cerema-pi.local:Desktop/Yolo_test/detections.json .
```