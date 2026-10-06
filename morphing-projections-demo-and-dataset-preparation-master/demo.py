"""
##################################################################

Morphing projections demo and dataset preparation

    GSDPI@MIDAS, Universidad de Oviedo, 2020

    Authors:
    Ignacio Díaz Blanco    <idiaz@uniovi.es>
    José M. Enguita        <jmenguita@uniovi.es>
    Ana González Muñiz     <agonzalez@isa.uniovi.es>
    Diego García Pérez     <diegogarcia@isa.uniovi.es>
    Abel A. Cuadrado Vega  <cuadrado@isa.uniovi.es>

	Supplemental material of:
    "Morphing Projections: a new visual technique for fast and interactive large-scale analysis of biomedical datasets"
    (submitted to Oxford Bioinformatics)

##################################################################
"""


# Supplementary material 1
#...

# Some needed packages
import numpy as np
import pandas as pd
from scipy.special import softmax
from matplotlib.colors import Normalize

# These are for using Bokeh as user interface
from bokeh.io import curdoc, show
from bokeh.layouts import row, column, widgetbox, layout, gridplot
from bokeh.models.callbacks import CustomJS
from bokeh.models import ColumnDataSource, LabelSet, HoverTool, TapTool
from bokeh.models import Circle, Div
from bokeh.models.widgets import Slider
from bokeh.plotting import figure, output_file
from bokeh.transform import factor_mark
from bokeh.colors import RGB


path_data = 'data/temp/'


# Some functions to keep the main code clearer

# Define two kinds of encodings: 
# - A circular encoding for a set of categories.
# - A linear encoding for both a set of categories and continuous values. 
#   (horizontally or vertically arranged).

def circularEncoding(N,keyString):
	"""
	DESCRIPTION
	Produces a dataframe E, containing the N positions equally distributed
	in a circle. 
	The N positions are associated to the N classes of a given category, respectively. 
	It is assumed that:
		- The N classes are exhaustive (the encoding includes all the possible classes in the category)
		- The classes are defined by an integer 0,...,N-1

	INPUTS
	    N: Number of classes in the encoding (ej. 7, to represent weekdays)
	    keyString: String identifier for the encoding (ej. "weekday")

	OUTPUTS
	    E: Encoding (dataframe with the class number and the position)
	"""

	x = np.arange(N)
	pos = np.vstack((np.cos(2*np.pi*x/N),np.sin(2*np.pi*x/N))).T

	E   = pd.DataFrame(pos,x,columns=['posx','posy'])
	E[keyString] = x
	return E

def linearEnc(df, col, dir='ver'):
    """
	DESCRIPTION
	Produces a 2D array with the (x,y) position for each entry of column 'col' the dataframe 'df'. 
	The function deals with class-valued variables, producing positions which are equally distributed
    over a line, or proportional to the variable value int its full range. The line direction can be
    vertical (default), or horizontal, depending on parameter 'dir'

	INPUTS
	    df: dataframe containing the data
        col: column of data to be used for the encoding
	    dir: encoding direction: 'ver' (default) for vertical. Horizontal otherwise

	OUTPUTS
	    pos: two-dimensional array with positions (x,y) for each entry in the column
	"""

    from sklearn import preprocessing

    # This code tries to create a reasonable span depending on the number of classes in the
    # variable.

    if (len(df[col].unique()) < 3 or len(df[col].unique()) > 35):
        rr = 50
    elif (len(df[col].unique()) > 10):
        rr = 150
    else:
        rr = 50 * len(df[col].unique())/2
    mms = preprocessing.MinMaxScaler(feature_range=[-rr, rr])
    if dir == 'ver':
        pos = np.hstack((0*df[col].values[:, None],
                         mms.fit_transform(df[col].values[:, None])))
    else:
        pos = np.hstack(
            (mms.fit_transform(df[col].values[:, None]), 0*df[col].values[:, None]))
    return pos


# Load data from files
def load_data():

    # Some global variables
    global df                           # Pancancer+metadata dataframe
    global E                            # Encoding matrix
    global encoding_variable_list       # List of variables used in encodings
    global clinical_data_list           # Full list of available clinical data
    global encoding_name                # Encoding names

    global path_data                    # path to data folder

    # Read the pancancer+metadata dataframe
    df = pd.read_hdf(path_data + 'pancancer_with_metadata.hdf')

    # Read the dataframe containing t-SNE training results
    df_morphing = pd.read_hdf(path_data + 'pancancer_morphing.hdf')
    
    # Generate the encodings for t-SNE data
    E = []
    encoding_name = []
    E.append(df_morphing[['genes_x', 'genes_y']].values)
    encoding_name.append('genes')
    E.append(df_morphing[['mirna_x', 'mirna_y']].values)
    encoding_name.append('mirna')


    # List with names for the encoding variables representing clinical data
    encoding_variable_list = ['cancer', 'type', 'race', 'gender', 'ethnicity',
                                 'primary_diagnosis', 'has_metastasis', 'vital_status']
    
    # List of full clinical data
    clinical_data_list =['cancer', 'type', 'race', 'gender', 'ethnicity', 'tumor_stage',
                                 'morphology', 'site_of_resection_or_biopsy', 'primary_diagnosis', 'has_metastasis', 'vital_status']


    # Add circular encodings for the above clinical variables
    for i in encoding_variable_list:
        print('generating encoding for variable ' + i + '...')

        pos = df[[i+'#']].merge(circularEncoding(max(df[i+'#'])+1, i+'#'),
                                on=i+'#', how='left')[['posx', 'posy']].values
        encoding_name.append(i)
        E.append(200*pos)

    # Add cancer and stage vertical linear encodings
    encoding_name.append('cancer (ver)')
    E.append(linearEnc(df, 'cancer#', 'ver'))

    encoding_name.append('tumor_stage (ver)')
    E.append(linearEnc(df, 'tumor_stage#', 'ver'))
    
    # Add linear encodings for some miRNA and genes

    encoding_name.append('miRNA-210-3p (hor)')
    E.append(linearEnc(df, 'MIMAT0000267', 'hor'))

    encoding_name.append('CA9 (ver)')
    E.append(linearEnc(df, 'CA9', 'ver'))

    encoding_name.append('SAA1 (hor)')
    E.append(linearEnc(df, 'SAA1', 'hor'))

    return


# Update the source used in the Bokeh plot

def update_source(df):
    from matplotlib import cm
    global colores

    aux = pd.concat([
        df['tumor'],
        #df['submitter_id'],
        df[clinical_data_list]],
        axis=1)

    # Create the source
    source = ColumnDataSource(aux)

    # Prepare coloring by cancer type
    colores = [RGB(*cm.nipy_spectral(i, bytes=True)[:3]) for i in Normalize(
        vmin=df['cancer#'].values.min(), vmax=df['cancer#'].values.max())(df['cancer#'].values)]
    
    
    # Add encodings to the source
    # They must be given as a (n_samples,2*num_encodings) matrix
    source.data['E'] = np.concatenate(E, axis=1).tolist()

    # Assign colors
    source.data['color'] = colores

    # note: we assign a weight of 50% to the base encoding E[0]
    #       so that, when the rest of encodings have a value of zero, the base encoding emerges
    z = np.zeros(len(encoding_name))
    z[0] = 0.5
    a = softmax(10*z)

    Epos = np.zeros([len(E[0]), 2])
    for i in range(len(encoding_name)):
        Epos = Epos + a[i]*E[i]

    source.data['pos_x'] = Epos[:, 0]
    source.data['pos_y'] = Epos[:, 1]

    return source


##############################################################################
# START OF PROGRAM
##############################################################################

load_data()
source = update_source(df)

#######################################################
# BOKEH Figures
#######################################################

plot = figure(plot_height=800, plot_width=1200, title="Cancer map",
              tools="crosshair,pan,reset,save,wheel_zoom,box_select,lasso_select",
              x_range=[-300, 300], y_range=[-225, 225], output_backend='webgl')

plt = plot.circle('pos_x', 'pos_y',
  source=source,color='color',legend='cancer', size=6, alpha=0.6, #radius=0.5,
  nonselection_alpha=0.3,line_color='#000000')

# Create a custom hover tool to show the value of the clinical data

custom_hover = HoverTool()
str = '<style>.bk-tooltip>div:not(:first-child){display:none;}</style><b>Sample: </b> @tumor <br>'

for i in clinical_data_list:
    str = str+'<b>{}:</b> @{}<br>'.format(i, i)

custom_hover.tooltips = str

plot.tools.append(custom_hover)

#######################################################
# SLIDERS
#######################################################

sliders = []
for i in encoding_name:
    sliders.append(Slider(title=i, value=0, start=0,
                          end=1, step=0.01, width=200, height=39))

sliders[0].value = 0.5

# Callback for sliders. This is the code that implements the morphing
# using the Softmax function.
# It is implemented in Javascript, so it is executed locally. This way
# it is much more efficient, and provides fluid interaction.
# The parameters are: the data source, the Encoding map, and the
# list of slider widgets.
CodeJS = """
  // the encoding weights are defined by the slider values
  var z =  s.map(x=>x.value)

  // apply a sensibility coefficient (sens = 10)
  z = z.map(x => x*10)  

  // use softmax function to obtain the weight coefficients "a"
  var ez      = z.map(x => Math.exp(x))       // exponents of z_i
  var sum_ez = ez.reduce( (x,v) => x + v)     // sum of exponents of z_i 
  var a       = ez.map( x => x/sum_ez)        // exponents of z_i / sum of exponents of z_i 


  // calculate encodings x weights
  var Epos = []
  var N = source.data['E'].length
  for (var j=0; j< N; j++ )
  {
  Epos[j] = [0,0]
  for (var i=0; i< a.length; i++)
    {
    Epos[j][0] += a[i]*source.data['E'][j][2*i]
    Epos[j][1] += a[i]*source.data['E'][j][2*i+1]
    }
  }


  // update coordinates x,y in the data source
  source.data['pos_x'] = Epos.map(x => x[0])
  source.data['pos_y'] = Epos.map(x => x[1])
  source.change.emit()

"""

# Install callback
update_data = CustomJS(args=dict(source=source,  s=sliders), code=CodeJS)
for s in sliders:
    s.js_on_change('value', update_data)

##########################################
# Layout
##########################################

layout = gridplot([plot, widgetbox(sliders)], ncols=2)


curdoc().add_root(layout)
curdoc().title = "morphing pancancer (demo)"

output_file('demo.html')
show(layout)
