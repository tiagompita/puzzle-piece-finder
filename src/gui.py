import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageDraw, ImageFont
import os
import threading
import time

class _TooltipManager:
    def __init__(self, root):
        self.root = root
        self.tip = None

    def bind(self, widget, text):
        widget.bind('<Enter>', lambda _e: self.show(widget, text))
        widget.bind('<Leave>', lambda _e: self.hide())

    def show(self, widget, text):
        self.hide()
        x = widget.winfo_rootx() + 10
        y = widget.winfo_rooty() + widget.winfo_height() + 5
        self.tip = tk.Toplevel(self.root)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        lbl = ttk.Label(self.tip, text=text, background='#ffffe0', relief='solid', borderwidth=1, padding=(6, 4))
        lbl.pack()

    def hide(self):
        if self.tip:
            self.tip.destroy()
            self.tip = None

class PuzzleGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Puzzle Solver GUI")
        self.geometry("1100x700")
        self.minsize(1000, 650)
        self._tooltip = _TooltipManager(self)
        self.pieces_imgs = []
        self.current_piece_idx = 0
        self.matching_cancelled = False  # Para controlar cancelamento
        self.last_results = []  # Resultados do último matching (dados, para export/visualização)
        self._build_widgets()

    def _build_widgets(self):
        # Layout: main (left) | logs (right)
        root_paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        root_paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        main = ttk.Frame(root_paned, width=750, height=600)
        logs = ttk.Frame(root_paned, width=320, height=600)
        main.pack_propagate(False)
        logs.pack_propagate(False)
        root_paned.add(main, weight=4)
        root_paned.add(logs, weight=1)

        # Controls (top)
        controls = ttk.Labelframe(main, text='Controls')
        controls.pack(fill=tk.X, pady=(0, 6))

        row1 = ttk.Frame(controls)
        row1.pack(fill=tk.X, pady=3)
        ttk.Button(row1, text="Load Puzzle", command=self.load_puzzle).pack(side=tk.LEFT)
        ttk.Button(row1, text="Load Pieces", command=self.load_pieces).pack(side=tk.LEFT, padx=(6, 0))
        segment_btn = ttk.Button(row1, text="Segment Photo", command=self.segment_pieces_photo)
        segment_btn.pack(side=tk.LEFT, padx=(6, 0))
        self._tooltip.bind(segment_btn, "Detetar e recortar peças automaticamente a partir de uma foto do monte.")
        ttk.Label(row1, text="Real puzzle W (cm):").pack(side=tk.LEFT, padx=(12, 4))
        self.width_entry = ttk.Entry(row1, width=8)
        self.width_entry.pack(side=tk.LEFT)
        ttk.Label(row1, text="H (cm):").pack(side=tk.LEFT, padx=(8, 4))
        self.height_entry = ttk.Entry(row1, width=8)
        self.height_entry.pack(side=tk.LEFT)

        row2 = ttk.Frame(controls)
        row2.pack(fill=tk.X, pady=3)
        ttk.Label(row2, text="#Pieces:").pack(side=tk.LEFT)
        self.pieces_entry = ttk.Entry(row2, width=8)
        self.pieces_entry.pack(side=tk.LEFT, padx=(4, 10))
        self.downscale_var = tk.BooleanVar(value=True)
        self.downscale_cb = ttk.Checkbutton(row2, text="Downscale", variable=self.downscale_var)
        self.downscale_cb.pack(side=tk.LEFT, padx=(0, 10))
        self.gpu_var = tk.BooleanVar(value=False)
        self.gpu_cb = ttk.Checkbutton(row2, text="GPU", variable=self.gpu_var)
        self.gpu_cb.pack(side=tk.LEFT)
        self._tooltip.bind(self.downscale_cb, "Coarse downscale do puzzle para acelerar; refina em full-res no fim.")
        self._tooltip.bind(self.gpu_cb, "Usa OpenCV CUDA se disponível; caso contrário, usa CPU automaticamente.")

        row3 = ttk.Frame(controls)
        row3.pack(fill=tk.X, pady=3)
        compute_btn = ttk.Button(row3, text="Compute Metrics", command=self.compute_metrics)
        compute_btn.pack(side=tk.LEFT)
        match_btn = ttk.Button(row3, text="Match", command=self.match_current_piece)
        match_btn.pack(side=tk.LEFT, padx=(6, 0))
        match_all_btn = ttk.Button(row3, text="Match All Pieces", command=self.match_all_pieces)
        match_all_btn.pack(side=tk.LEFT, padx=(6, 0))
        cancel_btn = ttk.Button(row3, text="Cancel", command=self.cancel_matching, state='disabled')
        cancel_btn.pack(side=tk.LEFT, padx=(6, 0))
        clear_btn = ttk.Button(row3, text="Clear Overlay", command=lambda: self.puzzle_canvas.delete("overlay"))
        clear_btn.pack(side=tk.LEFT, padx=(6, 0))
        export_btn = ttk.Button(row3, text="Export Results", command=self.export_results)
        export_btn.pack(side=tk.LEFT, padx=(6, 0))
        save_img_btn = ttk.Button(row3, text="Save Annotated Image", command=self.save_annotated_result)
        save_img_btn.pack(side=tk.LEFT, padx=(6, 0))

        # Guardar referência aos botões para controle de estado
        self.compute_btn = compute_btn
        self.match_btn = match_btn
        self.match_all_btn = match_all_btn
        self.cancel_btn = cancel_btn
        
        # Tooltips para os botões
        self._tooltip.bind(compute_btn, "Calcular métricas de tamanho e cobertura das peças.")
        self._tooltip.bind(match_btn, "Matching apenas da peça atualmente mostrada no display.")
        self._tooltip.bind(match_all_btn, "Matching simultâneo de todas as peças carregadas com traçados identificados.")
        self._tooltip.bind(cancel_btn, "Cancelar o processo de matching em andamento.")
        self._tooltip.bind(clear_btn, "Limpar todos os traçados/overlays do puzzle.")
        self._tooltip.bind(export_btn, "Exportar resultados para arquivo JSON.")
        self._tooltip.bind(save_img_btn, "Guardar imagem do puzzle anotada com marcador vermelho no centro de cada peça.")

        # Puzzle + Piece side by side
        center_row = ttk.Frame(main)
        center_row.pack(fill=tk.BOTH, expand=True)

        # Puzzle display
        puzzle_frame = ttk.Frame(center_row)
        puzzle_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Label(puzzle_frame, text="Puzzle").pack(anchor='w')
        self.puzzle_canvas = tk.Canvas(puzzle_frame, background="#1f1f1f", highlightthickness=1, highlightbackground="#555")
        self.puzzle_canvas.pack(fill=tk.BOTH, expand=True, padx=2, pady=(2, 0))

        # Piece navigation and display
        piece_panel = ttk.Labelframe(center_row, text='Piece')
        piece_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(8, 0))
        piece_panel.pack_propagate(False)
        piece_panel.configure(width=240, height=160)
        nav_frame = ttk.Frame(piece_panel)
        nav_frame.pack(fill=tk.X, pady=(0,2))
        ttk.Button(nav_frame, text="<", width=2, command=self.prev_piece).pack(side=tk.LEFT, padx=(2,2))
        ttk.Button(nav_frame, text=">", width=2, command=self.next_piece).pack(side=tk.LEFT, padx=(2,2))
        self.piece_canvas = ttk.Label(piece_panel, text="Piece Image", relief=tk.SUNKEN)
        self.piece_canvas.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # Logs
        ttk.Label(logs, text="Logs").pack(anchor='w')
        
        # Progress bar para matching
        self.progress_frame = ttk.Frame(logs)
        self.progress_frame.pack(fill=tk.X, pady=(0, 4))
        self.progress_bar = ttk.Progressbar(self.progress_frame, mode='indeterminate')
        self.progress_label = ttk.Label(self.progress_frame, text="", font=("Arial", 8))
        self.progress_label.pack()
        # Progress bar inicialmente oculta
        
        self.text = tk.Text(logs, height=10, wrap='word')
        yscroll = ttk.Scrollbar(logs, orient='vertical', command=self.text.yview)
        self.text.configure(yscrollcommand=yscroll.set)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _show_progress(self, message="Processando..."):
        """Mostrar barra de progresso."""
        self.progress_label.config(text=message)
        self.progress_bar.pack(fill=tk.X)
        self.progress_bar.start(10)
        self.update_idletasks()

    def _hide_progress(self):
        """Esconder barra de progresso."""
        self.progress_bar.stop()
        self.progress_bar.pack_forget()
        self.progress_label.config(text="")
        self.update_idletasks()

    def _disable_buttons(self):
        """Desabilitar botões durante processamento."""
        if hasattr(self, 'match_btn'):
            self.match_btn.configure(state='disabled')
        if hasattr(self, 'match_all_btn'):
            self.match_all_btn.configure(state='disabled')
        if hasattr(self, 'compute_btn'):
            self.compute_btn.configure(state='disabled')
        if hasattr(self, 'cancel_btn'):
            self.cancel_btn.configure(state='normal')  # Habilitar cancelar
        self.matching_cancelled = False  # Reset flag

    def _enable_buttons(self):
        """Reabilitar botões após processamento."""
        if hasattr(self, 'match_btn'):
            self.match_btn.configure(state='normal')
        if hasattr(self, 'match_all_btn'):
            self.match_all_btn.configure(state='normal')
        if hasattr(self, 'compute_btn'):
            self.compute_btn.configure(state='normal')
        if hasattr(self, 'cancel_btn'):
            self.cancel_btn.configure(state='disabled')  # Desabilitar cancelar

    def _disable_widget_buttons(self, widget, button_texts):
        """Recursivamente desabilitar botões por texto."""
        if isinstance(widget, ttk.Button):
            if widget.cget('text') in button_texts:
                widget.configure(state='disabled')
        for child in widget.winfo_children():
            self._disable_widget_buttons(child, button_texts)

    def _enable_widget_buttons(self, widget, button_texts):
        """Recursivamente reabilitar botões por texto."""
        if isinstance(widget, ttk.Button):
            if widget.cget('text') in button_texts:
                widget.configure(state='normal')
        for child in widget.winfo_children():
            self._enable_widget_buttons(child, button_texts)

    def prev_piece(self):
        if self.pieces_imgs:
            self.current_piece_idx = (self.current_piece_idx - 1) % len(self.pieces_imgs)
            self._display_piece_by_idx(self.current_piece_idx)

    def next_piece(self):
        if self.pieces_imgs:
            self.current_piece_idx = (self.current_piece_idx + 1) % len(self.pieces_imgs)
            self._display_piece_by_idx(self.current_piece_idx)

    def _display_piece_by_idx(self, idx):
        if not self.pieces_imgs:
            return
        piece = self.pieces_imgs[idx]
        self._display_image(piece['img_annotated'], self.piece_canvas, 'piece')
        piece_type = piece.get('piece_type')
        if piece.get('is_cluster'):
            self._log(f"⚠️ Peça {piece['id']}: CLUSTER (não é uma peça única).")
        elif piece_type:
            self._log(f"Peça {piece['id']}: tipo={piece_type}.")

    def load_puzzle(self):
        path = filedialog.askopenfilename(title="Select Puzzle Image", initialdir=self._default_puzzle_dir())
        if not path:
            return
        try:
            self.puzzle_img = Image.open(path)
            self._display_image(self.puzzle_img, self.puzzle_canvas, 'puzzle')
            self._log(f"Puzzle carregado: {path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load puzzle: {e}")

    def load_pieces(self):
        paths = filedialog.askopenfilenames(title="Select Piece Images", initialdir=self._default_piece_dir(), filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.bmp")])
        if not paths:
            return
        self.pieces_imgs = []
        for idx, path in enumerate(paths):
            try:
                img = Image.open(path)
                img_ = self._annotate_piece_number(img, idx + 1)
                self.pieces_imgs.append({'img': img, 'img_annotated': img_, 'id': idx+1, 'path': path})
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load piece: {path}\n{e}")
        if self.pieces_imgs:
            self.current_piece_idx = 0
            self._display_piece_by_idx(0)

    def _annotate_piece_number(self, img, number):
        """Devolver uma cópia de img com um número (1-based) desenhado no canto superior esquerdo."""
        img_ = img.copy()
        draw = ImageDraw.Draw(img_)
        try:
            font = ImageFont.truetype("arial.ttf", 60)
        except Exception:
            font = ImageFont.load_default()
        draw.rectangle([0,0,70,50], fill=(255,255,255,200))
        draw.text((8,2), str(number), fill=(0,0,0), font=font)
        return img_

    def _annotate_piece_extra(self, img, number, piece_type=None, is_cluster=False):
        """Como `_annotate_piece_number`, mas também mostra `piece_type` e marca
        visualmente clusters (borda vermelha + tag "CLUSTER") vindos da segmentação."""
        img_ = self._annotate_piece_number(img, number)
        draw = ImageDraw.Draw(img_)
        try:
            small_font = ImageFont.truetype("arial.ttf", 28)
        except Exception:
            small_font = ImageFont.load_default()

        if is_cluster:
            w, h = img_.size
            draw.rectangle([0, 0, w - 1, h - 1], outline=(255, 0, 0), width=8)
            label = "CLUSTER"
            draw.rectangle([0, h - 40, 160, h], fill=(255, 0, 0))
            draw.text((6, h - 36), label, fill=(255, 255, 255), font=small_font)
        elif piece_type:
            w, h = img_.size
            label = str(piece_type)
            text_w = max(60, len(label) * 16)
            draw.rectangle([0, h - 34, text_w, h], fill=(255, 255, 255, 200))
            draw.text((6, h - 30), label, fill=(0, 0, 0), font=small_font)

        return img_

    def segment_pieces_photo(self):
        """Detetar e recortar automaticamente peças a partir de uma foto do monte."""
        path = filedialog.askopenfilename(
            title="Select Pieces Photo",
            initialdir=self._default_piece_dir(),
            filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.bmp;*.dng"), ("All files", "*.*")]
        )
        if not path:
            return

        try:
            expected_pieces = int(self.pieces_entry.get()) if self.pieces_entry.get().strip() else None
        except ValueError:
            expected_pieces = None

        self._show_progress("Segmentando foto...")
        self._disable_buttons()

        def segmentation_thread():
            from .segmentation import segment_pieces_from_file
            try:
                result = segment_pieces_from_file(path, expected_pieces=expected_pieces)
                self.after(0, lambda: self._handle_segmentation_result(result, path))
            except Exception as e:
                error_msg = str(e)
                self.after(0, lambda: self._handle_segmentation_result({'error': error_msg, 'count': 0}, path))

        thread = threading.Thread(target=segmentation_thread, daemon=True)
        thread.start()

    def _handle_segmentation_result(self, result, path):
        """Processar resultado da segmentação automática (thread principal)."""
        self._hide_progress()
        self._enable_buttons()

        if 'error' in result:
            self._log(f"❌ Segmentação falhou ({result['error']}). Tenta uma foto mais próxima ou uma superfície lisa/contrastante.")
            return

        pieces = result.get('pieces', [])
        count = result.get('count', len(pieces))

        if pieces:
            from .edges import classify_pieces
            classify_pieces(pieces)
            # classify_pieces overwrites piece_type; is_cluster is the
            # authoritative flag, so restore piece_type='cluster' for those.
            for p in pieces:
                if p.get('is_cluster'):
                    p['piece_type'] = 'cluster'

        self.pieces_imgs = []
        for p in pieces:
            self.pieces_imgs.append({
                'img': p['image'],
                'img_annotated': self._annotate_piece_extra(p['image'], p['index'] + 1, p.get('piece_type'), p.get('is_cluster', False)),
                'id': p['index'] + 1,
                'path': f"{path}#piece{p['index'] + 1}",
                'mask': p['mask'],
                'bbox': p['bbox'],
                'piece_type': p.get('piece_type'),
                'is_cluster': p.get('is_cluster', False),
            })

        self.last_results = []

        if self.pieces_imgs:
            self.current_piece_idx = 0
            self._display_piece_by_idx(0)

        self._log(f"✅ Segmentação: {count} peças detetadas.")

        try:
            expected_pieces = int(self.pieces_entry.get()) if self.pieces_entry.get().strip() else None
        except ValueError:
            expected_pieces = None
        if expected_pieces is not None and expected_pieces != count:
            self._log(f"⚠️  Número de peças esperado ({expected_pieces}) difere do detetado ({count}).")

    def _display_image(self, img, widget, kind):
        if kind == 'piece' and hasattr(self, 'piece_canvas'):
            self.piece_canvas.update_idletasks()
            max_w = self.piece_canvas.winfo_width()
            max_h = self.piece_canvas.winfo_height()
            if max_w < 10 or max_h < 10:
                max_w, max_h = 240, 160
        elif kind == 'puzzle':
            # Para o puzzle, usar o tamanho do canvas
            if hasattr(widget, 'winfo_width'):
                widget.update_idletasks()
                max_w = widget.winfo_width()
                max_h = widget.winfo_height()
                if max_w < 50 or max_h < 50:
                    max_w, max_h = 600, 400
            else:
                max_w, max_h = 600, 400
        else:
            max_w, max_h = 240, 160
        
        w, h = img.size
        scale = min(max_w / w, max_h / h, 1.0)
        new_size = (int(w * scale), int(h * scale))
        img_resized = img.resize(new_size, Image.Resampling.LANCZOS)
        tk_img = ImageTk.PhotoImage(img_resized)
        
        if kind == 'puzzle':
            # Para Canvas (puzzle)
            widget.delete("image")  # Remove imagem anterior
            widget.create_image(max_w//2, max_h//2, anchor='center', image=tk_img, tags="image")
            widget.image = tk_img  # Manter referência
        else:
            # Para Label (pieces)
            try:
                widget.configure(image=tk_img, text='')
            except Exception:
                pass
            widget.image = tk_img

    def _log(self, text):
        self.text.insert(tk.END, text + "\n")
        self.text.see(tk.END)

    def _default_puzzle_dir(self):
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'images', 'puzzles'))
        return base if os.path.isdir(base) else os.getcwd()

    def _default_piece_dir(self):
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'images', 'pieces'))
        return base if os.path.isdir(base) else os.getcwd()

    def match_all_pieces(self):
        """Matching otimizado para todas as peças carregadas simultaneamente."""
        if not hasattr(self, 'puzzle_img'):
            self._log("❌ Carregue primeiro uma imagem do puzzle!")
            return
            
        if not self.pieces_imgs:
            self._log("❌ Carregue pelo menos uma peça!")
            return
        
        if len(self.pieces_imgs) == 1:
            # Se só há uma peça, usar o método para peça única
            self.match_current_piece()
            return
            
        # Obter parâmetros
        try:
            num_pieces = int(self.pieces_entry.get()) if self.pieces_entry.get().strip() else len(self.pieces_imgs)
        except ValueError:
            num_pieces = len(self.pieces_imgs)
        
        self._show_progress(f"Matching {len(self.pieces_imgs)} peças...")
        self._disable_buttons()
        
        def matching_all_thread():
            try:
                results = self._perform_batch_matching(num_pieces)
                self.after(0, lambda: self._handle_batch_results(results))
            except Exception as e:
                self.after(0, lambda: self._handle_batch_error(e))
        
        thread = threading.Thread(target=matching_all_thread, daemon=True)
        thread.start()

    def cancel_matching(self):
        """Cancelar processo de matching em andamento."""
        self.matching_cancelled = True
        self._log("🛑 Cancelamento solicitado...")
        self._hide_progress()
        self._enable_buttons()
        # Limpar qualquer overlay parcial
        self.puzzle_canvas.delete("overlay")

    def _perform_batch_matching(self, num_pieces):
        """Executar matching de múltiplas peças com otimizações."""
        results = []
        total_pieces = len(self.pieces_imgs)
        skipped_clusters = 0

        for i, piece_data in enumerate(self.pieces_imgs):
            # Verificar se foi cancelado
            if self.matching_cancelled:
                self.after(0, lambda: self._log("🛑 Matching cancelado pelo usuário."))
                break

            piece_id = piece_data['id']

            if piece_data.get('is_cluster'):
                skipped_clusters += 1
                self.after(0, lambda pid=piece_id: self._log(f"⚠️ Peça {pid} é um cluster — ignorada no matching."))
                continue

            piece_img = piece_data['img']

            # Atualizar progresso
            progress_msg = f"Processando peça {piece_id} ({i+1}/{total_pieces})"
            self.after(0, lambda msg=progress_msg: self._show_progress(msg))
            
            try:
                # Usar o método otimizado
                result = self._perform_optimized_matching(piece_img, piece_id, num_pieces)
                
                if "error" not in result:
                    # Extrair informações do resultado
                    best_pos = result.get("best_position", (0, 0))
                    scale = result.get("scale", 1.0)
                    similarity = result.get("refined_similarity", 0.0)
                    piece_size = result.get("piece_size_final", piece_img.size)
                    
                    results.append({
                        'piece_id': piece_id,
                        'position': best_pos,
                        'size': piece_size,
                        'similarity': similarity,
                        'scale': scale,
                        'color': "#0066FF",
                        'path': piece_data.get('path')
                    })
                    
                    # Log no thread principal
                    self.after(0, lambda pid=piece_id, pos=best_pos, sim=similarity, sc=scale: 
                              self._log(f"     ✅ Peça {pid}: pos=({pos[0]}, {pos[1]}), sim={sim:.1%}, escala={sc:.2f}"))
                else:
                    self.after(0, lambda pid=piece_id, err=result['error']: 
                              self._log(f"     ❌ Peça {pid}: {err}"))
                    
            except Exception as e:
                self.after(0, lambda pid=piece_id, err=str(e):
                          self._log(f"     ❌ Erro peça {pid}: {err}"))
                continue

        if skipped_clusters:
            self.after(0, lambda n=skipped_clusters: self._log(f"⚠️ {n} peça(s) ignorada(s) por serem clusters."))

        return results

    def _handle_batch_results(self, results):
        """Processar resultados do batch matching."""
        self._hide_progress()
        self._enable_buttons()
        
        if results:
            # Reter resultados como dados (para export/visualização)
            self.last_results = results

            # Limpar overlays anteriores
            self.puzzle_canvas.delete("overlay")

            # Analisar e reportar resultados
            self._analyze_multi_piece_results(results)
            self._draw_piece_overlays(results)
            self._log(f"✅ Matching completo! {len(results)}/{len(self.pieces_imgs)} peças processadas com sucesso.")
        else:
            self._log("❌ Nenhuma peça foi processada com sucesso.")

    def _handle_batch_error(self, error):
        """Processar erro do batch matching."""
        self._hide_progress()
        self._enable_buttons()
        self._log(f"❌ Erro no matching em lote: {str(error)}")

    def _analyze_multi_piece_results(self, results):
        """Analisar resultados do matching de múltiplas peças."""
        if len(results) < 2:
            return
            
        # Estatísticas básicas
        similarities = [r['similarity'] for r in results]
        scales = [r['scale'] for r in results]
        
        avg_sim = sum(similarities) / len(similarities)
        avg_scale = sum(scales) / len(scales)
        
        self._log(f"📊 Estatísticas do matching:")
        self._log(f"   Similaridade média: {avg_sim:.1%}")
        self._log(f"   Escala média: {avg_scale:.2f}")
        
        # Detectar sobreposições potenciais
        overlaps = []
        for i, r1 in enumerate(results):
            for j, r2 in enumerate(results[i+1:], i+1):
                if self._check_overlap(r1, r2):
                    overlaps.append((r1['piece_id'], r2['piece_id']))
        
        if overlaps:
            self._log(f"⚠️  Sobreposições detectadas: {overlaps}")
        else:
            self._log("✅ Nenhuma sobreposição detectada.")

    def _check_overlap(self, result1, result2, threshold=0.3):
        """Verificar se duas peças se sobrepõem significativamente."""
        x1, y1 = result1['position']
        w1, h1 = result1['size']
        
        x2, y2 = result2['position']
        w2, h2 = result2['size']
        
        # Calcular área de interseção
        left = max(x1, x2)
        top = max(y1, y2)
        right = min(x1 + w1, x2 + w2)
        bottom = min(y1 + h1, y2 + h2)
        
        if left >= right or top >= bottom:
            return False  # Sem interseção
        
        intersection_area = (right - left) * (bottom - top)
        area1 = w1 * h1
        area2 = w2 * h2
        min_area = min(area1, area2)
        
        return (intersection_area / min_area) > threshold

    def _puzzle_pixels_per_cm(self):
        """Derivar pixels/cm do puzzle a partir das dimensões reais (como em compute_metrics).

        Retorna um float (px/cm) ou None se o utilizador não forneceu medidas.
        Usa a largura primeiro (puzzle_w / real_width), com fallback para a altura.
        """
        if not hasattr(self, 'puzzle_img'):
            return None
        puzzle_w, puzzle_h = self.puzzle_img.size
        try:
            real_width = float(self.width_entry.get()) if self.width_entry.get().strip() else None
            real_height = float(self.height_entry.get()) if self.height_entry.get().strip() else None
        except (ValueError, AttributeError):
            return None
        if real_width:
            return puzzle_w / real_width
        if real_height:
            return puzzle_h / real_height
        return None

    def export_results(self):
        """Exportar resultados reais do matching para arquivo JSON."""
        if not hasattr(self, 'puzzle_img'):
            self._log("❌ Carregue primeiro uma imagem do puzzle!")
            return

        # Guarda: o matching tem de ter sido executado (baseado nos dados retidos).
        if not self.last_results:
            self._log("❌ Execute primeiro o matching das peças.")
            return

        try:
            from tkinter import filedialog
            import json
            from datetime import datetime

            # Preparar dados para exportação
            export_data = {
                "timestamp": datetime.now().isoformat(),
                "puzzle_info": {
                    "size": list(self.puzzle_img.size),
                    "mode": self.puzzle_img.mode
                },
                "matched_pieces_count": len(self.last_results),
                "total_pieces_loaded": len(self.pieces_imgs),
                "pieces": []
            }

            # Escala px/cm ao nível do puzzle (se o utilizador forneceu medidas reais).
            px_per_cm = self._puzzle_pixels_per_cm()
            if px_per_cm is not None:
                export_data["pixels_per_cm"] = px_per_cm

            # Serializar os resultados reais de cada peça.
            for r in self.last_results:
                pos = r.get('position', (0, 0))
                size = r.get('size', (0, 0))
                sim = r.get('similarity')
                sc = r.get('scale')
                piece_entry = {
                    "id": r.get('piece_id'),
                    "position": {"x": int(pos[0]), "y": int(pos[1])},
                    "size": {"width": int(size[0]), "height": int(size[1])},
                    "similarity": float(sim) if sim is not None else None,
                    "scale": float(sc) if sc is not None else None,
                }
                if r.get('path'):
                    piece_entry["path"] = r['path']
                export_data["pieces"].append(piece_entry)

            # Salvar arquivo
            filename = filedialog.asksaveasfilename(
                title="Salvar resultados",
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
            )

            if filename:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, indent=2, ensure_ascii=False)
                self._log(f"✅ Resultados exportados para: {filename} "
                          f"({len(self.last_results)}/{len(self.pieces_imgs)} peças).")

        except Exception as e:
            self._log(f"❌ Erro ao exportar: {str(e)}")

    def save_annotated_result(self):
        """Guardar uma imagem do puzzle anotada com um marcador vermelho no centro provável de cada peça.

        Usa src/visualization.py para renderizar os resultados retidos sobre self.puzzle_img
        e guarda o ficheiro através de um diálogo. Não afeta os overlays interativos do canvas.
        """
        if not hasattr(self, 'puzzle_img'):
            self._log("❌ Carregue primeiro uma imagem do puzzle!")
            return

        if not self.last_results:
            self._log("❌ Execute primeiro o matching das peças.")
            return

        try:
            from tkinter import filedialog
            from .visualization import save_annotated_image

            filename = filedialog.asksaveasfilename(
                title="Guardar imagem anotada",
                defaultextension=".png",
                filetypes=[("PNG image", "*.png"), ("JPEG image", "*.jpg;*.jpeg"), ("All files", "*.*")]
            )

            if filename:
                save_annotated_image(self.puzzle_img, self.last_results, filename)
                self._log(f"✅ Imagem anotada guardada em: {filename}")

        except Exception as e:
            self._log(f"❌ Erro ao guardar imagem anotada: {str(e)}")

    def compute_metrics(self):
        """Calcular métricas das imagens carregadas."""
        if not hasattr(self, 'puzzle_img'):
            self._log("❌ Carregue primeiro uma imagem do puzzle!")
            return
            
        self._log("📊 Computando métricas do puzzle...")
        
        # Métricas básicas do puzzle
        puzzle_w, puzzle_h = self.puzzle_img.size
        puzzle_area = puzzle_w * puzzle_h
        
        self._log(f"   Puzzle: {puzzle_w}x{puzzle_h}px (área: {puzzle_area:,}px)")
        
        # Métricas das peças (se carregadas)
        if self.pieces_imgs:
            self._log(f"📊 Métricas das {len(self.pieces_imgs)} peças carregadas:")
            
            total_piece_area = 0
            for piece_data in self.pieces_imgs:
                piece_w, piece_h = piece_data['img'].size
                piece_area = piece_w * piece_h
                total_piece_area += piece_area
                
                area_ratio = (piece_area / puzzle_area) * 100
                self._log(f"   Peça {piece_data['id']}: {piece_w}x{piece_h}px "
                         f"(área: {piece_area:,}px, {area_ratio:.1f}% do puzzle)")
            
            coverage = (total_piece_area / puzzle_area) * 100
            self._log(f"   Cobertura total: {coverage:.1f}% do puzzle")
            
            # Estimativa de escala real (se fornecida)
            try:
                real_width = float(self.width_entry.get()) if self.width_entry.get().strip() else None
                real_height = float(self.height_entry.get()) if self.height_entry.get().strip() else None
                
                if real_width:
                    px_per_cm = puzzle_w / real_width
                    self._log(f"   Escala: {px_per_cm:.1f} pixels/cm")
                    
                    if real_height:
                        expected_height = puzzle_h / px_per_cm
                        self._log(f"   Altura estimada: {expected_height:.1f}cm")
                        
            except ValueError:
                pass
        else:
            self._log("   Nenhuma peça carregada para análise.")

    def match_current_piece(self):
        """Executar matching apenas da peça atualmente exibida no display."""
        if not hasattr(self, 'puzzle_img'):
            self._log("❌ Carregue primeiro uma imagem do puzzle!")
            return
            
        if not self.pieces_imgs:
            self._log("❌ Carregue pelo menos uma peça!")
            return
            
        # Obter a peça atualmente exibida
        current_piece_data = self.pieces_imgs[self.current_piece_idx]
        piece_img = current_piece_data['img']
        piece_id = current_piece_data['id']

        if current_piece_data.get('is_cluster'):
            self._log(f"⚠️ Peça {piece_id} é um cluster (não é uma peça única) — não é localizável.")
            return

        # Executar em thread para não travar a GUI
        self._show_progress(f"Matching peça {piece_id}...")
        self._disable_buttons()
        
        def matching_thread():
            try:
                # Adicionar timeout para evitar travamentos
                import time
                start_time = time.time()
                
                result = self._perform_optimized_matching(piece_img, piece_id)
                
                elapsed_time = time.time() - start_time
                self.after(0, lambda: self._log(f"⏱️ Matching completado em {elapsed_time:.1f}s"))
                
                # Usar after para executar no thread principal
                self.after(0, lambda: self._handle_single_match_result(result, piece_id))
            except Exception as e:
                error_msg = str(e)  # Capturar a mensagem de erro
                self.after(0, lambda: self._handle_match_error(error_msg, piece_id))
        
        thread = threading.Thread(target=matching_thread, daemon=True)
        thread.start()

    def _perform_optimized_matching(self, piece_img, piece_id, num_pieces=None):
        """Executar matching otimizado com configurações de performance."""
        # Obter parâmetros
        try:
            if num_pieces is None:
                num_pieces = int(self.pieces_entry.get()) if self.pieces_entry.get().strip() else None
        except ValueError:
            num_pieces = None
            
        use_downscale = self.downscale_var.get()
        use_gpu = self.gpu_var.get()
        
        # Log dos parâmetros
        if use_gpu:
            self.after(0, lambda: self._log("🚀 Tentando usar GPU para matching..."))
        
        # Log de debug dos tamanhos
        puzzle_w, puzzle_h = self.puzzle_img.size
        piece_w, piece_h = piece_img.size
        self.after(0, lambda: self._log(f"🔍 Debug: Puzzle {puzzle_w}x{puzzle_h}, Peça {piece_w}x{piece_h}, num_pieces={num_pieces}"))
        
        # Importar módulos
        from .matching import multi_scale_template_match
        
        # Configurações otimizadas
        optimized_params = {
            'puzzle_img': self.puzzle_img,
            'piece_img': piece_img,
            'num_pieces': num_pieces,
            'use_downscale': True,  # Sempre usar downscale para velocidade
            'use_gpu': use_gpu,  # Usar a opção escolhida pelo usuário
            'method': 'SQDIFF_NORMED'  # Método mais rápido
        }
        
        # Se a imagem for grande, fazer downscale mais agressivo para evitar travamentos
        puzzle_w, puzzle_h = self.puzzle_img.size
        scale_factor_applied = None
        if puzzle_w * puzzle_h > 1500 * 1500:  # Limite menor para evitar travamentos
            # Para puzzles grandes, reduzir significativamente
            scale_factor = min(1200 / puzzle_w, 1200 / puzzle_h, 1.0)
            if scale_factor < 1.0:
                new_w = int(puzzle_w * scale_factor)
                new_h = int(puzzle_h * scale_factor)
                puzzle_resized = self.puzzle_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                optimized_params['puzzle_img'] = puzzle_resized
                scale_factor_applied = scale_factor  # Guardar separadamente
        
        # Adicionar controle de erro para GPU
        try:
            # Executar matching (sem passar _scale_factor)
            result = multi_scale_template_match(**optimized_params)
            
            # Log de sucesso
            if use_gpu:
                self.after(0, lambda: self._log("✅ Matching com GPU concluído com sucesso"))
            
        except Exception as e:
            error_msg = str(e).lower()
            # Verificar diferentes tipos de erro relacionados à GPU
            gpu_error_keywords = ["gpu", "cuda", "opencl", "device"]
            is_gpu_error = use_gpu and any(keyword in error_msg for keyword in gpu_error_keywords)
            
            if is_gpu_error:
                self.after(0, lambda: self._log("⚠️ GPU não disponível, usando CPU..."))
                optimized_params['use_gpu'] = False
                try:
                    result = multi_scale_template_match(**optimized_params)
                    self.after(0, lambda: self._log("✅ Matching com CPU concluído"))
                except Exception as cpu_error:
                    raise cpu_error
            else:
                raise e
        
        # Ajustar posições se houve downscale
        if scale_factor_applied is not None:
            if 'best_position' in result:
                pos_x, pos_y = result['best_position']
                result['best_position'] = (int(pos_x / scale_factor_applied), int(pos_y / scale_factor_applied))
            if 'piece_size_final' in result:
                size_w, size_h = result['piece_size_final']
                result['piece_size_final'] = (int(size_w / scale_factor_applied), int(size_h / scale_factor_applied))
        
        return result

    def _handle_single_match_result(self, result, piece_id):
        """Processar resultado de matching de peça única."""
        self._hide_progress()
        self._enable_buttons()
        
        if "error" in result:
            self._log(f"   ❌ Erro no matching: {result['error']}")
            return
        
        # Extrair informações do resultado
        best_pos = result.get("best_position", (0, 0))
        scale = result.get("scale", 1.0)
        similarity = result.get("refined_similarity", 0.0)
        piece_size = result.get("piece_size_final", self.pieces_imgs[self.current_piece_idx]['img'].size)
        
        # Limpar overlays anteriores e desenhar novo
        self.puzzle_canvas.delete("overlay")
        
        current_piece = self.pieces_imgs[self.current_piece_idx]
        result_data = [{
            'piece_id': piece_id,
            'position': best_pos,
            'size': piece_size,
            'similarity': similarity,
            'scale': scale,
            'color': "#0066FF",
            'path': current_piece.get('path')
        }]

        # Reter resultados como dados (para export/visualização)
        self.last_results = result_data
        self._draw_piece_overlays(result_data)
        
        self._log(f"✅ Peça {piece_id}: pos=({best_pos[0]}, {best_pos[1]}), "
                 f"similaridade={similarity:.1%}, escala={scale:.2f}")

    def _handle_match_error(self, error, piece_id):
        """Processar erro de matching."""
        self._hide_progress()
        self._enable_buttons()
        self._log(f"❌ Erro processando peça {piece_id}: {str(error)}")

    def _draw_piece_overlays(self, results):
        """Desenhar retângulos e identificadores para cada peça no puzzle canvas."""
        # Obter dimensões do canvas e da imagem
        self.puzzle_canvas.update_idletasks()
        canvas_w = self.puzzle_canvas.winfo_width()
        canvas_h = self.puzzle_canvas.winfo_height()
        
        if not hasattr(self, 'puzzle_img'):
            return
            
        img_w, img_h = self.puzzle_img.size
        
        # Calcular escala de exibição (mesmo cálculo usado em _display_image)
        max_w, max_h = canvas_w, canvas_h
        if max_w < 50 or max_h < 50:
            max_w, max_h = 600, 400
            
        scale = min(max_w / img_w, max_h / img_h, 1.0)
        display_w = int(img_w * scale)
        display_h = int(img_h * scale)
        
        # Posição da imagem no canvas (centralizada)
        offset_x = (canvas_w - display_w) // 2
        offset_y = (canvas_h - display_h) // 2
        
        # Desenhar overlay para cada peça
        for result in results:
            piece_id = result['piece_id']
            pos_x, pos_y = result['position']
            piece_w, piece_h = result['size']
            color = result['color']
            similarity = result['similarity']
            
            # Converter coordenadas da imagem para coordenadas do canvas
            canvas_x1 = offset_x + int(pos_x * scale)
            canvas_y1 = offset_y + int(pos_y * scale)
            canvas_x2 = canvas_x1 + int(piece_w * scale)
            canvas_y2 = canvas_y1 + int(piece_h * scale)
            
            # Desenhar retângulo da peça
            self.puzzle_canvas.create_rectangle(
                canvas_x1, canvas_y1, canvas_x2, canvas_y2,
                outline=color, width=3, tags="overlay"
            )
            
            # Desenhar identificador da peça (número menor e mais legível)
            text = str(piece_id)
            text_x = canvas_x1 + 5
            text_y = canvas_y1 + 5
            
            # Fundo branco menor para o número
            text_width = len(text) * 8
            text_height = 16
            self.puzzle_canvas.create_rectangle(
                text_x - 4, text_y - 4, 
                text_x + text_width, text_y + text_height,
                fill="white", outline=color, width=2, tags="overlay"
            )
            
            # Número do identificador (fonte menor e mais legível)
            self.puzzle_canvas.create_text(
                text_x, text_y, anchor="nw",
                text=text, fill=color, font=("Arial", 12, "bold"),
                tags="overlay"
            )
            
            # Similaridade em texto menor abaixo
            sim_text = f"({similarity:.0%})"
            self.puzzle_canvas.create_text(
                text_x, text_y + 26, anchor="nw",
                text=sim_text, fill=color, font=("Arial", 10),
                tags="overlay"
            )

def main():
    app = PuzzleGUI()
    app.mainloop()

if __name__ == "__main__":
    main()