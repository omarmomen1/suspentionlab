import os
import codecs

replacements = {
    "m/sÂ²": "m/s²",
    "kgÂ·mÂ²": "kg·m²",
    "NÂ·s/m": "N·s/m",
    "Â·": "·",
    "(Â°)": "(°)",
    "Â°/s": "°/s",
    "âˆ’": "−",
    "â†’": "→",
    "Ï†": "phi",
    "Ï†Ì‡": "phi_dot",
    "Î¸": "theta",
    "Î¸Ì‡": "theta_dot",
    "Â°": "°"
}

app_dir = r"C:\Users\omaar\Downloads\project\frontend2\app"

for root, dirs, files in os.walk(app_dir):
    for file in files:
        if file.endswith(".tsx"):
            path = os.path.join(root, file)
            with codecs.open(path, "r", "utf-8") as f:
                text = f.read()
            
            original_text = text
            for bad, good in replacements.items():
                text = text.replace(bad, good)
            
            if text != original_text:
                with codecs.open(path, "w", "utf-8") as f:
                    f.write(text)
                print(f"Fixed {path}")

print("All done!")
