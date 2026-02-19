from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import ezdxf
import math
import os
import re
from pyproj import Transformer

app = Flask(__name__)
CORS(app)

# --- CONFIGURAÇÃO DE COORDENADAS (SIRGAS 2000 / UTM 24S) ---
# EPSG:4674 (Geral Brasil) -> EPSG:31984 (UTM 24S)
transformer = Transformer.from_crs("epsg:4674", "epsg:31984", always_xy=True)

def gms_para_decimal(gms_str, sentido):
    """Converte 12°58'26,036\" para decimal"""
    try:
        # Extrai os números ignorando os símbolos °, ', "
        partes = re.findall(r"(\d+[\.,]?\d*)", gms_str)
        graus = float(partes[0].replace(',', '.'))
        minutos = float(partes[1].replace(',', '.'))
        segundos = float(partes[2].replace(',', '.'))
        
        decimal = graus + (minutos / 60) + (segundos / 3600)
        # Sul e Oeste são negativos
        if sentido in ['S', 'W', 'O']:
            decimal = -decimal
        return decimal
    except:
        return None

# --- ROTA 1: GEOCONVERTER (JÁ VALIDADA 100%) ---
@app.route('/convert', methods=['POST'])
def convert():
    if 'dxf_file' not in request.files:
        return "Nenhum arquivo enviado", 400
    file = request.files['dxf_file']
    input_path = "temp_in.dxf"
    output_path = "temp_out.dxf"
    file.save(input_path)
    try:
        doc_in = ezdxf.readfile(input_path)
        msp_in = doc_in.modelspace()
        doc_out = ezdxf.new('R2010')
        blk = doc_out.blocks.new(name='SIG_PONTO')
        blk.add_circle((0, 0), radius=0.2)
        blk.add_line((-0.3, 0), (0.3, 0))
        blk.add_line((0, -0.3), (0, 0.3))
        blk.add_attdef(tag='ID', text='ID', insert=(0.4, 0.4), dxfattribs={'height': 0.3})
        msp_out = doc_out.modelspace()
        contador_p = 1
        pontos = msp_in.query('POINT')
        textos = msp_in.query('TEXT')
        for p in pontos:
            px, py = p.dxf.location.x, p.dxf.location.y
            id_f = next((t.dxf.text for t in textos if math.sqrt((px-t.dxf.insert.x)**2 + (py-t.dxf.insert.y)**2) < 3.0), f"P{contador_p}")
            if id_f.startswith("P") and id_f[1:].isdigit(): contador_p += 1
            block_ref = msp_out.add_blockref('SIG_PONTO', (px, py), dxfattribs={'layer': 'VERTICES_ENGETECH'})
            block_ref.add_auto_attribs({'ID': id_f})
        doc_out.saveas(output_path)
        return send_file(output_path, as_attachment=True, download_name="Engetech_Convertido.dxf")
    except Exception as e: return str(e), 500
    finally:
        if os.path.exists(input_path): os.remove(input_path)

# --- ROTA 2: GEOEXTRATOR (ADAPTADA PARA SEUS MEMORIAIS GMS) ---
@app.route('/extract_text', methods=['POST'])
def extract_text():
    data = request.get_json()
    texto = data.get('texto', '')
    
    # 1. Busca nomes de vértices (Ex: RRGL-P-28391)
    nomes_vertices = re.findall(r"RRGL-[PV]-\d+", texto)
    
    # 2. Busca coordenadas GMS (Ex: 12°58'26,036"S)
    lats = re.findall(r"(\d+°\d+'\d+[\.,]?\d*\"S)", texto)
    lons = re.findall(r"(\d+°\d+'\d+[\.,]?\d*\"W)", texto)
    
    vertices_utm = []
    for i in range(min(len(lats), len(lons))):
        lat_dec = gms_para_decimal(lats[i], 'S')
        lon_dec = gms_para_decimal(lons[i], 'W')
        # Converte Geográfico para UTM SIRGAS 2000
        x_utm, y_utm = transformer.transform(lon_dec, lat_dec)
        vertices_utm.append((x_utm, y_utm))

    if not vertices_utm:
        return "Erro: Formato de coordenada não reconhecido.", 400

    output_path = "Engetech_Extraido.dxf"
    doc = ezdxf.new('R2010')
    doc.layers.new('POLIGONAL_ENGETECH', dxfattribs={'color': 1})
    doc.layers.new('VERTICES', dxfattribs={'color': 2})
    msp = doc.modelspace()
    
    # Desenha a poligonal e os blocos
    msp.add_lwpolyline(vertices_utm, dxfattribs={'closed': True, 'layer': 'POLIGONAL_ENGETECH'})
    for i, v in enumerate(vertices_utm):
        nome = nomes_vertices[i] if i < len(nomes_vertices) else f"V{i+1}"
        msp.add_circle(v, radius=1.0, dxfattribs={'layer': 'VERTICES'})
        txt = msp.add_text(nome, dxfattribs={'height': 1.5, 'layer': 'VERTICES'})
        txt.set_placement((v[0] + 1.5, v[1] + 1.5))
        
    doc.saveas(output_path)
    return send_file(output_path, as_attachment=True, download_name="Engetech_Poligonal.dxf")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
