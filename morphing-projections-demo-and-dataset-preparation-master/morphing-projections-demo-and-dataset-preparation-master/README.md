### Supplementary material
## Morphing Projections: a new visual technique for fast and interactive large-scale analysis of biomedical datasets
#### Ignacio Díaz, José M. Enguita, Ana González, Diego García, Abel A. Cuadrado, María D. Chiara and Nuria Valdés

This repository is part of the supplementary material of the article, and contains all the necessary files to replicate the examples and case studies. In addition, the demo program is interactive and fully functional, so the user may explore himself the potential of the Morphing Projections technique with real data from TCGA. Just download the file and open it with your usual internet browser.

### Demo program
The demo program (`demo.html`) is a standalone application that can be run on any Internet browser. It contains all the necessary data, so no further action is needed to go through the case studies or explore the data. Steps: a) download `demo.html` to a folder, and b) open it with the browser.

### Files
| File           |Purpose                                                                          |
|:------------------------------|:-----------------------------------------------------------------|
| `demo.html`  | Demo program ready to run in any browser. |
| `get_and_process_tcga_data.ipynb` | Jupyter Notebook script with code and instructions for downloading and processing data.|
| `demo.py` | Source code to build the demo program using the previously downloaded and processed data.|


### Downloading data
The user may prefer to download and process the data himself. The file `get_and_process_tcga_data.ipynb` contains both Python code and instructions to guide the user through the process. The script downloads DNA and miRNA expression levels from [The Xena Functional Genomics Explorer](https://xenabrowser.net/datapages/?hub=https://tcga.xenahubs.net:443) (University of California - Santa Cruz) in a new folder `data/downloaded_data`. It also instructs the user to manually download the clinical dataset from the [GDC Portal](https://portal.gdc.cancer.gov/exploration?facetTab=clinical&filters=%7B%22op%22%3A%22and%22%2C%22content%22%3A%5B%7B%22op%22%3A%22in%22%2C%22content%22%3A%7B%22field%22%3A%22genes.is_cancer_gene_census%22%2C%22value%22%3A%5B%22true%22%5D%7D%7D%5D%7D).

### Processing data
The same file contains code to process the downloaded data and training the neccessary tSNE views. This data is stored in the `data/temp` folder.

**BEWARE:** The training of the tSNEs includes a random initialization, so the graphical representation of the data, while retaining its significance, may vary from the original demo program.


### Note
Data used to produce the `demo.html` was fetched on 2020/03/05. Please keep in mind that original datasets from the remote repositories might undergo changes in the code. The code has been tested on 2020/05/14.
