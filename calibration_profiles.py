"""Practical tolerance for the portrait green-base/red-cover reference."""
from copy import deepcopy

def comfortable_station_one(current):
    station=deepcopy(current)
    base={'x':0.23,'y':0.29,'w':0.53,'h':0.53}
    red={'x':0.23,'y':0.50,'w':0.53,'h':0.32}
    station['anchor'].update(roi=base.copy(),min_area_ratio=0.16)
    for step in station['steps']:
        step['stable_seconds']=0.4
        if step['color']=='green':
            step.update(roi=base.copy(),min_area_ratio=0.18,max_area_ratio=0.95,
                        min_aspect_ratio=0.48,max_aspect_ratio=1.50)
        elif step['color']=='red':
            step.update(roi=red.copy(),min_area_ratio=0.30,max_area_ratio=0.95,
                        min_aspect_ratio=1.10,max_aspect_ratio=2.00,
                        relative_to_anchor=[-0.25,0.25,0.10,1.15])
    return station
