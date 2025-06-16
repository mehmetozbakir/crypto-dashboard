import os

def merge_python_files(input_folder=".", output_file="merged_code.txt"):
    """
    Klasördeki tüm .py dosyalarını sırayla okuyup, tek bir metin dosyası halinde birleştirir.
    """
    py_files = []
    
    # Tüm klasör ve alt klasörleri tarayarak .py dosyalarını topla
    for root, dirs, files in os.walk(input_folder):
        for f in files:
            if f.endswith(".py") and f != os.path.basename(__file__):
                py_files.append(os.path.join(root, f))
    
    # İsimlere göre sıralayalım ki dosyalar belirli bir düzende olsun (opsiyonel)
    py_files.sort()
    
    with open(output_file, "w", encoding="utf-8") as outfile:
        for py_file in py_files:
            outfile.write(f"\n# --- FILE: {py_file} ---\n\n")
            with open(py_file, "r", encoding="utf-8") as infile:
                content = infile.read()
                outfile.write(content)
                outfile.write("\n\n")
    
    print(f"{len(py_files)} adet .py dosyası birleştirildi. Çıktı: {output_file}")

if __name__ == "__main__":
    merge_python_files(".", "merged_code.txt")
