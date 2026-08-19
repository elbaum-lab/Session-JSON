# Session-JSON
GUI for storing STEM session metadata in JSON files

Designed by Shahar Seifer, Elbaum lab, Weizmann Institute of Science (2026)

Requirements
------------
Python 3.11 or newer

Instructions
------------
Copy the files to your local folder.    
Run as:
    python metadata_gui.py master.JSON  
First set the folder and master name of the dataset according to your storage convention. These define the JSON file to be generated.  
Fill out the categories: microscope name, sample, tilt series, single scan and its properties, the detector, and the beam.  
Loading a file at any window automatically fills out the branch of information according to the previous JSON file.  
Closing a window or clicking "Save" stores the file.  
The tilt angles list is determined by either dose symmetric order or a one directional order. The list may be edited directly in the text file since it is set to "arbitrary" automatically.  
The settings of "additional scans per tilt" allows for multiple scan modes at any visited tilt view.     
