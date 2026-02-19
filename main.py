from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import ezdxf
import math
import os
import re
import json
from pyproj import Transformer
from docx import Document
from fpdf import FPDF
from PIL import Image, ImageEnhance

app = Flask(__name__)
CORS(app)

transformer = Transformer.from_crs("epsg:4674", "epsg:31984", always_xy=True)

def calcular_azimute(p1, p2):
    dn, de = p2[1] - p1[1], p2[0] - p1[0]
    az_deg = (math.degrees(math.atan2(de, dn)) + 360) % 360
    d, m = int(az_deg), int((az_deg - int(az_deg)) * 60)
    s = round(((az_deg - d) * 60 - m) * 60)
    return f"{d}°{m}'{s}\""

# --- ROTAS GEOCONVERTER E EXTRACTOR (MANTIDAS 100%) ---
@app.route('/convert', methods=['POST'])
def convert():
    # ... (Código anterior do GeoConverter permanece idêntico)
    pass

@app.route('/extract_docx', methods=['POST'])
def extract_docx():
    # ... (Código anterior do GeoExtrator permanece idêntico)
    pass

# --- ROTA 3: GEOMEMORIAL (INTELIGÊNCIA HÍBRIDA) ---
@app.route('/generate_memorial_dxf', methods=['POST'])
def generate_memorial_dxf():
    dxf_file = request.files['dxf_file']
    logo = request.files.get('logo_file')
    data = request.form
    
    # Lista de confrontantes inseridos manualmente na Web
    conf_web = json.loads(data.get('confrontantes', '[]'))
    
    path_dxf = "mem_in.dxf"
    dxf_file.save(path_dxf)
    
    try:
        doc = ezdxf.readfile(path_dxf)
        msp = doc.modelspace()
        poly = msp.query('LWPOLYLINE').first
        vertices = list(poly.get_points())
        blocos = msp.query('INSERT[name=="SIG_PONTO"]')
        
        dados_vertices = []
        for v in vertices:
            info = {"id": "Ponto", "conf": "", "mat": "", "cns": "", "prop": ""}
            for b in blocos:
                if math.sqrt((v[0]-b.dxf.insert.x)**2 + (v[1]-b.dxf.insert.y)**2) < 1.0:
                    for attr in b.attribs:
                        tag = attr.dxf.tag.upper()
                        val = attr.dxf.text
                        if tag == 'ID': info["id"] = val
                        elif tag == 'CONFRONTANTE': info["conf"] = val
                        elif tag == 'MATRICULA': info["mat"] = val
                        elif tag == 'CNS': info["cns"] = val
                        elif tag == 'PROPRIEDADE': info["prop"] = val
            
            # SOBREPOSIÇÃO: Se houver dado manual da Web para este ID, ele substitui o do CAD
            for c in conf_web:
                if c['vertice'].upper() == info["id"].upper():
                    info["conf"] = c['nome']
                    info["mat"] = c.get('mat', '')
                    info["cns"] = c.get('cns', '')
                    info["prop"] = c.get('propriedade', '')
            
            dados_vertices.append(info)

        pdf = FPDF()
        pdf.add_page()
        
        # Marca d'água Verticalizada
        if logo:
            img = Image.open(logo).convert("RGBA")
            alpha = ImageEnhance.Brightness(img.split()[3]).enhance(0.12)
            img.putalpha(alpha)
            img.save("wm.png")
            pdf.image("wm.png", x=35, y=60, w=140)

        pdf.set_font("Times", 'B', 14)
        pdf.cell(190, 10, "MEMORIAL DESCRITIVO", ln=True, align='C')
        pdf.set_font("Times", size=10)
        pdf.multi_cell(190, 6, f"PROPRIETÁRIO: {data.get('prop_nome')}\nCPF: {data.get('prop_cpf')}\nIMÓVEL: {data.get('imovel_nome')}")
        pdf.ln(5); pdf.set_font("Times", size=11)

        # Construção do texto
        corpo = f"Inicia-se a descrição no vértice {dados_vertices[0]['id']}, de coordenadas N {vertices[0][1]:.3f}m e E {vertices[0][0]:.3f}m; "
        
        conf_atual = "vizinho indicado"
        for i in range(len(vertices)):
            p1, p2 = vertices[i], vertices[(i + 1) % len(vertices)]
            dist = math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2)
            id_prox = dados_vertices[(i + 1) % len(vertices)]['id']
            
            # Atualiza confrontante se houver nova definição neste vértice
            if dados_vertices[i]["conf"]:
                v_info = dados_vertices[i]
                conf_atual = f"{v_info['conf']} (Propriedade: {v_info['prop']}, Matrícula: {v_info['mat']}, CNS: {v_info['cns']})"

            corpo += f"deste, segue com azimute {calcular_azimute(p1, p2)} e distância {dist:.2f}m até o vértice {id_prox}, confrontando com {conf_atual}; "

        pdf.multi_cell(190, 8, corpo + " fechando o perímetro.", align='J')
        
        # Tabela de Coordenadas
        pdf.ln(10); pdf.set_font("Times", 'B', 8)
        pdf.cell(40, 7, "VÉRTICE", 1); pdf.cell(50, 7, "COORD. N (m)", 1); pdf.cell(50, 7, "COORD. E (m)", 1); pdf.cell(50, 7, "CONFRONTANTE", 1, ln=True)
        pdf.set_font("Times", size=7)
        for i, v in enumerate(vertices):
            pdf.cell(40, 6, dados_vertices[i]['id'], 1)
            pdf.cell(50, 6, f"{v[1]:.3f}", 1)
            pdf.cell(50, 6, f"{v[0]:.3f}", 1)
            pdf.cell(50, 6, dados_vertices[i]['conf'][:30], 1, ln=True)

        out_pdf = "Memorial_Engetech.pdf"
        pdf.output(out_pdf)
        return send_file(out_pdf, as_attachment=True)
    finally:
        if os.path.exists(path_dxf): os.remove(path_dxf)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
