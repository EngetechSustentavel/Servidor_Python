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
# Usamos EPSG:4674 para SIRGAS 2000 Geográfico e EPSG:31984 para UTM 24S
transformer = Transformer.from_crs("epsg:4674", "epsg:31984", always_xy=True)

def converter_para_utm(lat, lon):
    try:
        return transformer.transform(lon, lat)
    except:
        return None

# --- ROTA 1: GEOCONVERTER (FERRAMENTA 100% OK) ---
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
        pontos = msp_in.query('POINT')
        textos = msp_in.query('TEXT')
        
        contador_p = 1
        for p in pontos:
            px, py = p.dxf.location.x, p.dxf.location.y
            id_final = ""
            encontrou_texto = False
            for t in textos:
                tx, ty = t.dxf.insert.x, t.dxf.insert.y
                if math.sqrt((px-tx)**2 + (py-ty)**2) < 3.0:
                    id_final = str(t.dxf.text).strip()
                    encontrou_texto = True
                    break
            
            if not encontrou_texto or id_final == "":
                id_final = f"P{contador_p}"
                contador_p += 1
            
            block_ref = msp_out.add_blockref('SIG_PONTO', (px, py), dxfattribs={'layer': 'VERTICES_ENGETECH'})
            block_ref.add_auto_attribs({'ID': id_final})
            
        doc_out.saveas(output_path)
        return send_file(output_path, as_attachment=True, download_name="Engetech_Convertido.dxf")
    except Exception as e:
        return f"Erro: {str(e)}", 500
    finally:
        if os.path.exists(input_path): os.remove(input_path)

# --- ROTA 2: GEOEXTRATOR (NOVA FERRAMENTA) ---
@app.route('/extract_text', methods=['POST'])
def extract_text():
    data = request.get_json()
    texto = data.get('texto', '')
    
    # Busca por pares de números (UTM ou Lat/Long)
    padrao = re.findall(r"(-?\d[\d\.]*?\d,\d+|-?\d+\.\d+)", texto)
    
    vertices = []
    temp_coords = []
    
    for num in padrao:
        # Normaliza: remove pontos de milhar e troca vírgula por ponto decimal
        limpo = float(num.replace('.', '').replace(',', '.')) if ',' in num else float(num)
        temp_coords.append(limpo)
    
    # Agrupa em pares X e Y
    for i in range(0, len(temp_coords) - 1, 2):
        x, y = temp_coords[i], temp_coords[i+1]
        
        # Se for Lat/Long (números pequenos), converte para UTM
        if abs(x) < 180 and abs(y) < 180:
            utm = converter_para_utm(x, y) # lat, lon
            if utm: vertices.append(utm)
        else:
            vertices.append((x, y))

    if not vertices:
        return "Erro: Nenhuma coordenada identificada no texto.", 400

    output_path = "Engetech_Extracao.dxf"
    doc = ezdxf.new('R2010')
    msp = doc.modelspace()
    
    # Desenha a poligonal e identifica os vértices
    msp.add_lwpolyline(vertices, dxfattribs={'closed': True, 'layer': 'POLIGONAL_ENGETECH', 'color': 1})
    
    for i, v in enumerate(vertices):
        msp.add_circle(v, radius=1.0, dxfattribs={'layer': 'VERTICES'})
        msp.add_text(f"V{i+1}", dxfattribs={'height': 1.5}).set_placement(v)
    
    doc.saveas(output_path)
    return send_file(output_path, as_attachment=True, download_name="Engetech_Poligonal.dxf")

if __name__ == '__main__':
    # O Render usa a porta 10000 por padrão
    app.run(host='0.0.0.0', port=10000)
