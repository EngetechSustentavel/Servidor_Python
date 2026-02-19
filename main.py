from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import ezdxf
import math
import os
import re
from pyproj import Transformer
from docx import Document
from fpdf import FPDF
from PIL import Image, ImageEnhance

app = Flask(__name__)
CORS(app)

# --- CONFIGURAÇÃO GEOGRÁFICA SIRGAS 2000 ---
transformer = Transformer.from_crs("epsg:4674", "epsg:31984", always_xy=True)

def calcular_azimute(p1, p2):
    dn, de = p2[1] - p1[1], p2[0] - p1[0]
    az_deg = (math.degrees(math.atan2(de, dn)) + 360) % 360
    d, m = int(az_deg), int((az_deg - int(az_deg)) * 60)
    s = round(((az_deg - d) * 60 - m) * 60)
    return f"{d}°{m}'{s}\""

def gms_para_decimal(gms_str, sentido):
    try:
        partes = re.findall(r"(\d+[\.,]?\d*)", gms_str)
        decimal = float(partes[0]) + (float(partes[1]) / 60) + (float(partes[2].replace(',', '.')) / 3600)
        return -decimal if sentido in ['S', 'W', 'O'] else decimal
    except: return None

# --- ROTA 1: GEOCONVERTER (100% OK) ---
@app.route('/convert', methods=['POST'])
def convert():
    file = request.files['dxf_file']
    path_in, path_out = "conv_in.dxf", "conv_out.dxf"
    file.save(path_in)
    try:
        doc_in = ezdxf.readfile(path_in)
        msp_in = doc_in.modelspace()
        doc_out = ezdxf.new('R2010')
        blk = doc_out.blocks.new(name='SIG_PONTO')
        blk.add_circle((0, 0), radius=0.2)
        blk.add_attdef(tag='ID', text='ID', insert=(0.4, 0.4), dxfattribs={'height': 0.3})
        msp_out = doc_out.modelspace()
        contador_p = 1
        textos = msp_in.query('TEXT')
        for p in msp_in.query('POINT'):
            px, py = p.dxf.location.x, p.dxf.location.y
            id_f = next((t.dxf.text for t in textos if math.sqrt((px-t.dxf.insert.x)**2 + (py-t.dxf.insert.y)**2) < 3.0), f"P{contador_p}")
            if id_f == f"P{contador_p}": contador_p += 1
            br = msp_out.add_blockref('SIG_PONTO', (px, py), dxfattribs={'layer': 'VERTICES_ENGETECH'})
            br.add_auto_attribs({'ID': id_f})
        doc_out.saveas(path_out)
        return send_file(path_out, as_attachment=True)
    finally:
        if os.path.exists(path_in): os.remove(path_in)

# --- ROTA 2: GEOEXTRATOR (DOCX -> DXF) ---
@app.route('/extract_docx', methods=['POST'])
def extract_docx():
    file = request.files['docx_file']
    docx_path = "temp_ext.docx"
    file.save(docx_path)
    try:
        doc_word = Document(docx_path)
        texto = "\n".join([p.text for p in doc_word.paragraphs])
        lats = re.findall(r"(\d+°\d+'\d+[\.,]?\d*\"S)", texto)
        lons = re.findall(r"(\d+°\d+'\d+[\.,]?\d*\"W)", texto)
        vertices = []
        for i in range(min(len(lats), len(lons))):
            x, y = transformer.transform(gms_para_decimal(lons[i], 'W'), gms_para_decimal(lats[i], 'S'))
            vertices.append((x, y))
        doc_dxf = ezdxf.new('R2010')
        doc_dxf.layers.new('POLIGONAL', dxfattribs={'color': 1})
        msp = doc_dxf.modelspace()
        msp.add_lwpolyline(vertices, dxfattribs={'closed': True, 'layer': 'POLIGONAL'})
        out_ext = "Engetech_Extraido.dxf"
        doc_dxf.saveas(out_ext)
        return send_file(out_ext, as_attachment=True)
    finally:
        if os.path.exists(docx_path): os.remove(docx_path)

# --- ROTA 3: GEOMEMORIAL (DXF -> PDF COM MARCA D'ÁGUA) ---
@app.route('/generate_memorial_dxf', methods=['POST'])
def generate_memorial_dxf():
    dxf_file = request.files['dxf_file']
    logo = request.files.get('logo_file')
    data = request.form
    import json
    conf_list = json.loads(data.get('confrontantes', '[]')) # Lista do PHP
    
    path_dxf = "mem_in.dxf"
    dxf_file.save(path_dxf)
    
    try:
        doc = ezdxf.readfile(path_dxf)
        msp = doc.modelspace()
        poly = msp.query('LWPOLYLINE').first
        vertices = list(poly.get_points())
        blocos = msp.query('INSERT[name=="SIG_PONTO"]') # Busca seus blocos do CAD
        
        # 1. CAPTURA DE IDS DIRETAMENTE DOS ATRIBUTOS DO BLOCO
        ids_reais = []
        for v in vertices:
            nome_v = "Ponto"
            for b in blocos:
                if math.sqrt((v[0]-b.dxf.insert.x)**2 + (v[1]-b.dxf.insert.y)**2) < 1.0:
                    for attr in b.attribs:
                        if attr.dxf.tag == 'ID':
                            nome_v = attr.dxf.text
                            break
            ids_reais.append(nome_v)

        pdf = FPDF()
        pdf.add_page()
        
        # 2. MARCA D'ÁGUA SUAVE E VERTICALIZADA
        if logo:
            img = Image.open(logo).convert("RGBA")
            alpha = img.split()[3]
            alpha = ImageEnhance.Brightness(alpha).enhance(0.12) # 12% Opacidade
            img.putalpha(alpha)
            img.save("wm.png")
            pdf.image("wm.png", x=35, y=60, w=140)

        pdf.set_font("Times", 'B', 14)
        pdf.cell(190, 10, "MEMORIAL DESCRITIVO", ln=True, align='C')
        pdf.set_font("Times", size=10)
        pdf.multi_cell(190, 6, f"PROPRIETÁRIO: {data.get('prop_nome')}\nCPF: {data.get('prop_cpf')}\nIMÓVEL: {data.get('imovel_nome')}")
        pdf.ln(5); pdf.set_font("Times", size=11)

        # 3. CONSTRUÇÃO DO TEXTO COM CONFRONTANTES DINÂMICOS
        corpo = f"Inicia-se a descrição no vértice {ids_reais[0]}, de coordenadas N {vertices[0][1]:.3f} e E {vertices[0][0]:.3f}; "
        for i in range(len(vertices)):
            p1, p2 = vertices[i], vertices[(i + 1) % len(vertices)]
            dist = math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2)
            id_prox = ids_reais[(i + 1) % len(vertices)]
            
            # Busca se há troca de confrontante neste vértice
            conf_atual = "vizinho indicado"
            for c in conf_list:
                if c['vertice'].upper() == ids_reais[i].upper():
                    conf_atual = c['nome']

            corpo += f"deste, segue com azimute {calcular_azimute(p1, p2)} e distância {dist:.2f}m até o vértice {id_prox}, confrontando com {conf_atual}; "

        pdf.multi_cell(190, 8, corpo + " fechando o perímetro no ponto inicial.", align='J')
        
        out_pdf = "Memorial_Engetech.pdf"
        pdf.output(out_pdf)
        return send_file(out_pdf, as_attachment=True)
    finally:
        if os.path.exists(path_dxf): os.remove(path_dxf)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
