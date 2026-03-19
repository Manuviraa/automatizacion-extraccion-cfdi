import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd
import io

def procesar_factura_xml(archivo_subido):
    # Cargar y parsear el XML
    tree = ET.parse(archivo_subido)
    root = tree.getroot()
    ns = {
        'cfdi': 'http://www.sat.gob.mx/cfd/4',
        'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital'
    }

    # 1. Extracción de Identificadores y Fecha
    emisor = root.find('.//cfdi:Emisor', ns).attrib.get('Nombre', 'Sin emisor')
    receptor = root.find('.//cfdi:Receptor', ns).attrib.get('Nombre', 'Sin receptor')
    
    # Extracción de la fecha de emisión
    fecha_emision = root.attrib.get('Fecha', 'Sin fecha')
    
    tipo_letra = root.attrib.get('TipoDeComprobante', '')
    mapa_comprobantes = {'I': 'Ingreso', 'E': 'Egreso', 'T': 'Traslado', 'P': 'Pago', 'N': 'Nómina'}
    efecto_comprobante = mapa_comprobantes.get(tipo_letra, tipo_letra)
    
    # Múltiples conceptos unidos por <>
    lista_descripciones = [nodo.attrib.get('Descripcion', 'Sin descripción') 
                           for nodo in root.findall('.//cfdi:Conceptos/cfdi:Concepto', ns)]
    descripcion_unida = " <> ".join(lista_descripciones)
    
    folio_fiscal = root.find('.//cfdi:Complemento/tfd:TimbreFiscalDigital', ns).attrib.get('UUID')

    # 2. Extracción de Totales Base
    subtotal = float(root.attrib.get('SubTotal', 0.0))
    descuento = float(root.attrib.get('Descuento', 0.0))
    subtotal_neto = subtotal - descuento
    total_factura = float(root.attrib.get('Total', 0.0))

    # 3. Inicializar variables de impuestos
    iva_trasladado = 0.0
    ieps_trasladado = 0.0
    iva_retenido = 0.0
    isr_retenido = 0.0

    # 4. Búsqueda de Impuestos Globales
    traslados = root.findall('./cfdi:Impuestos/cfdi:Traslados/cfdi:Traslado', ns)
    for t in traslados:
        impuesto = t.attrib.get('Impuesto')
        importe = float(t.attrib.get('Importe', 0.0))
        if impuesto == '002':
            iva_trasladado += importe
        elif impuesto == '003':
            ieps_trasladado += importe

    retenciones = root.findall('./cfdi:Impuestos/cfdi:Retenciones/cfdi:Retencion', ns)
    for r in retenciones:
        impuesto = r.attrib.get('Impuesto')
        importe = float(r.attrib.get('Importe', 0.0))
        if impuesto == '002':
            iva_retenido += importe
        elif impuesto == '001':
            isr_retenido += importe

    # 5. Estructurar la fila con la fecha añadida al final
    fila = {
        "Nombre emisor": emisor,
        "Nombre receptor": receptor,
        "Efecto del comprobante": efecto_comprobante,
        "Descripción": descripcion_unida,
        "Subtotal": subtotal,
        "Descuento": descuento,
        "Subtotal Neto": round(subtotal_neto, 2),
        "IVA Trasladado": round(iva_trasladado, 2),
        "IEPS Trasladado": round(ieps_trasladado, 2),
        "IVA Retenido": round(iva_retenido, 2),
        "ISR Retenido": round(isr_retenido, 2),
        "Total (Calculado)": round(subtotal_neto + iva_trasladado + ieps_trasladado - iva_retenido - isr_retenido, 2),
        "Total (XML)": total_factura,
        "Folio Fiscal": folio_fiscal,
        "Fecha de Emisión": fecha_emision
    }
    return fila

# ==========================================
# INTERFAZ GRÁFICA DE STREAMLIT
# ==========================================

st.title("Procesador Automático de Facturas XML")
st.write("Sube los archivos XML descargados del portal del SAT para generar el reporte en Excel de manera automática.")

# Dividimos la pantalla en dos columnas para mayor claridad
col1, col2 = st.columns(2)

with col1:
    st.subheader("🟢 Comprobantes de Ingreso")
    archivos_ingresos = st.file_uploader("Arrastra aquí los XML de ingresos", type=['xml'], accept_multiple_files=True, key="ing")

with col2:
    st.subheader("🔴 Comprobantes de Egreso")
    archivos_egresos = st.file_uploader("Arrastra aquí los XML de egresos", type=['xml'], accept_multiple_files=True, key="egr")

# Botón central para ejecutar el código
if st.button("Procesar Facturas y Generar Excel", type="primary"):
    
    if not archivos_ingresos and not archivos_egresos:
        st.warning("⚠️ Por favor, sube al menos un archivo XML en alguna de las dos categorías para comenzar.")
    else:
        # Procesamos las listas de archivos
        datos_ing = [procesar_factura_xml(xml) for xml in archivos_ingresos] if archivos_ingresos else []
        datos_egr = [procesar_factura_xml(xml) for xml in archivos_egresos] if archivos_egresos else []
        
        # Convertimos a DataFrames
        df_ingresos = pd.DataFrame(datos_ing)
        df_egresos = pd.DataFrame(datos_egr)
        
        # Guardar en memoria usando io.BytesIO y ExcelWriter para las pestañas
        buffer_memoria = io.BytesIO()
        with pd.ExcelWriter(buffer_memoria, engine='openpyxl') as writer:
            if not df_ingresos.empty:
                df_ingresos.to_excel(writer, index=False, sheet_name='Ingresos')
            if not df_egresos.empty:
                df_egresos.to_excel(writer, index=False, sheet_name='Egresos')
        
        # Obtenemos el archivo creado en la memoria
        archivo_excel_final = buffer_memoria.getvalue()
        
        st.success("✅ ¡Análisis completado exitosamente! El archivo está listo.")
        
        # Botón para descargar el Excel resultante
        st.download_button(
            label="📥 Descargar Reporte en Excel",
            data=archivo_excel_final,
            file_name="Reporte_Mensual_Facturas.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
