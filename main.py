from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import ezdxf
import math
import os
import re
from pyproj import Transformer
from fpdf import FPDF
from PIL import Image

app = Flask(__name__)
CORS(app)

# --- CONFIGURAÇÃO GEOGRÁFICA ---
transformer = Transformer.from_crs("epsg:4674", "epsg:31984", always_xy=True)

def calcular_azimute(p1, p2):
    dn = p2[1] - p1[1]
    de = p2[0] - p1[0]
    az_rad = math.atan2(de, dn)
    az_deg = (math.degrees(az_rad) + 360) % 360
    d = int(az_deg)
    m = int((az_deg - d) * 60)
    s = round(((az_deg - d) * 60 - m) * 60)
    return f"{d}°{m}'{s}\""

# --- ROTA 1: GEOCONVERTER ---
@app.route('/convert', methods=['POST'])
def convert():
    file = request.files['dxf_file']
    path_in, path_out = "in.dxf", "out.dxf"
    file.save(path_in)
    try:
        doc = ezdxf.readfile(path_in)
        msp = doc.modelspace()
        out = ezdxf.new('R2010')
        blk = out.blocks.new(name='SIG_PONTO')
        blk.add_circle((0,0), 0.2)
        blk.add_attdef('ID', 'ID', (0.4, 0.4), dxfattribs={'height': 0.3})
        msp_out = out.modelspace()
        for i, p in enumerate(msp.query('POINT')):
            br = msp_out.add_blockref('SIG_PONTO', p.dxf.location, dxfattribs={'layer': 'VERTICES'})
            br.add_auto_attribs({'ID': f"P{i+1}"})
        out.saveas(path_out)
        return send_file(path_out, as_attachment=True)
    finally: os.remove(path_in) if os.path.exists(path_in) else None

# --- ROTA 2: GEOMEMORIAL (DXF -> PDF COM MARCA D'ÁGUA) ---
@app.route('/generate_memorial_dxf', methods=['POST'])
def generate_memorial_dxf():
    dxf_file = request.files['dxf_file']
    logo = request.files.get('logo_file')
    data = request.form
    
    path_dxf = "temp_memorial.dxf"
    dxf_file.save(path_dxf)
    
    try:
        doc = ezdxf.readfile(path_dxf)
        msp = doc.modelspace()
        # Busca a polilinha da poligonal
        poly = msp.query('LWPOLYLINE').first
        vertices = poly.get_points()
        
        pdf = FPDF()
        pdf.add_page()
        
        if logo:
            logo.save("logo_mem.png")
            pdf.image("logo_mem.png", x=50, y=90, w=110) # Marca d'água
            
        pdf.set_font("Times", 'B', 14)
        pdf.cell(190, 10, "MEMORIAL DESCRITIVO", ln=True, align='C')
        pdf.set_font("Times", size=10)
        pdf.multi_cell(190, 6, f"PROPRIETÁRIO: {data.get('prop_nome')}\nCPF: {data.get('prop_cpf')}\nIMÓVEL: {data.get('imovel_nome')}")
        
        pdf.ln(5)
        pdf.set_font("Times", size=11)
        
        corpo_texto = f"Inicia-se a descrição no vértice V1... "
        # Lógica de iteração para azimutes e distâncias
        for i in range(len(vertices)):
            p1 = vertices[i]
            p2 = vertices[(i + 1) % len(vertices)]
            dist = math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2)
            az = calcular_azimute(p1, p2)
            corpo_texto += f"segue com azimute {az} e distância {dist:.2f}m até o vértice V{i+2 if i+1 < len(vertices) else 1}; "

        pdf.multi_cell(190, 7, corpo_texto, align='J')
        
        path_pdf = "Memorial_Engetech.pdf"
        pdf.output(path_pdf)
        return send_file(path_pdf, as_attachment=True)
    finally: os.remove(path_dxf)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
