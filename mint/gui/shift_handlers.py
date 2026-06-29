"""Signal shift handlers for DIST dialog and drag operations."""

import re
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QModelIndex

import iplotLogging.setupLogger as Sl

logger = Sl.get_logger(__name__)

if TYPE_CHECKING:
    from iplotlib.core.canvas import Canvas


class ShiftHandlerMixin:
    """Mixin providing signal shift functionality for MTMainWindow."""

    # Attributes provided by host class
    qtcanvas: Any
    sigCfgWidget: Any
    canvasStack: Any
    dataRangeSelector: Any
    canvas: 'Canvas'
    _shift_original_exprs: dict
    _shift_accumulated: dict

    def _connect_shift_signals(self):
        """Connect shift-related Qt signals."""
        self.qtcanvas.signalShiftRequested.connect(self._on_signal_shift_requested)
        self.qtcanvas.signalShiftApplied.connect(self._on_signal_shift_applied)
        self.qtcanvas.signalShiftUndone.connect(self._on_signal_shift_undone)
        self.qtcanvas.signalShiftPulseApplied.connect(self._on_signal_shift_pulse_applied)
        self.qtcanvas.signalShiftPulseUndone.connect(self._on_signal_shift_pulse_undone)

    def _init_shift_storage(self):
        """Initialize shift tracking dictionaries."""
        self._shift_original_exprs = {}
        self._shift_accumulated = {}
        self._shift_mother_original_pulse_id = {}  # Key: (Variable, DS) -> original PulseId
        self._shift_undo_in_progress = False  # Guard to skip row-removal handler during undo

    def _format_offset_expr(self, base_expr: str, offset: float) -> str:
        """Format expression with offset, using subtraction for negative values."""
        if abs(offset) < 1e-10:
            return base_expr
        if offset >= 0:
            return f"({base_expr}) + {offset}"
        return f"({base_expr}) - {abs(offset)}"

    def _update_signal_label_and_legend(self, signal_uid: str, label: str):
        """Update signal label, line label and rebuild legend for a shifted signal."""
        original_signal, original_plot = self._find_signal_in_canvas(signal_uid)
        if not original_signal:
            return
        original_signal.label = label
        if hasattr(original_signal, 'lines') and original_signal.lines:
            line = original_signal.lines[0]
            if hasattr(line, 'set_label'):
                line.set_label(label)
        w = self.canvasStack.currentWidget()
        if w and original_plot:
            impl_plot = w._parser._signal_impl_plot_lut.get(signal_uid)
            if impl_plot:
                w._parser.rebuild_legend(impl_plot, original_plot)

    def _set_row_xy(self, model, row_idx: int, new_x: str, new_y: str):
        """Set x/y expression values on a model row."""
        df = model.get_dataframe()
        if 'x' in df.columns:
            model.setData(model.createIndex(row_idx, df.columns.get_loc('x')), new_x, 2)
        if 'y' in df.columns:
            model.setData(model.createIndex(row_idx, df.columns.get_loc('y')), new_y, 2)

    def _build_offset_expressions_from(self, model, original_x: str, original_y: str,
                                        total_dx: float, total_dy: float):
        """Build x/y offset expressions from explicit originals (no tracking lookup)."""
        bp = getattr(model, 'blueprint', {}) or {}
        default_x = (bp.get('x') or {}).get('default') or '${self}.time'
        default_y = (bp.get('y') or {}).get('default') or '${self}.data'
        base_x = original_x if original_x else default_x
        base_y = original_y if original_y else default_y
        new_x = self._format_offset_expr(base_x, total_dx) if abs(total_dx) > 1e-10 else (original_x or '')
        new_y = self._format_offset_expr(base_y, total_dy) if abs(total_dy) > 1e-10 else (original_y or '')
        return new_x, new_y

    # ------------------------------------------------------------------
    # Shift applied / undone handlers (direct drag, no pulse isolation)
    # ------------------------------------------------------------------

    def _on_signal_shift_applied(self, signal_uid: str, dx: float, dy: float, source: str):
        """Update table expressions when inline shift is applied."""
        model = self.sigCfgWidget.model
        df = model.get_dataframe()

        row_idx = self._find_row_by_uid(df, signal_uid)
        if row_idx is None:
            return

        if signal_uid not in self._shift_original_exprs:
            self._shift_original_exprs[signal_uid] = {
                'x': df.at[row_idx, 'x'] if 'x' in df.columns else '',
                'y': df.at[row_idx, 'y'] if 'y' in df.columns else '',
                'original_alias': df.at[row_idx, 'Alias'] if 'Alias' in df.columns else ''
            }
            self._shift_accumulated[signal_uid] = {'dx': 0.0, 'dy': 0.0}

        self._shift_accumulated[signal_uid]['dx'] += dx
        self._shift_accumulated[signal_uid]['dy'] += dy
        new_x, new_y = self._build_offset_expressions(
            model, signal_uid,
            self._shift_accumulated[signal_uid]['dx'],
            self._shift_accumulated[signal_uid]['dy']
        )
        self._set_row_xy(model, row_idx, new_x, new_y)

        # Set alias on the inline row so the shifted signal is identifiable
        df = model.get_dataframe()
        if 'Alias' in df.columns:
            current_alias = df.at[row_idx, 'Alias']
            original_alias = self._shift_original_exprs[signal_uid].get('original_alias', '')
            # Only generate alias if the row doesn't already have a shifted alias
            if not current_alias or current_alias == original_alias:
                var_name = df.at[row_idx, 'Variable'] if 'Variable' in df.columns else ''
                shifted_alias = self._generate_unique_alias(model, var_name, 'shifted',
                                                            row_alias=original_alias)
                model.setData(model.createIndex(row_idx, df.columns.get_loc('Alias')), shifted_alias, 2)
                self._update_signal_label_and_legend(signal_uid, shifted_alias)

    def _on_signal_shift_undone(self, signal_uid: str, dx: float, dy: float, source: str):
        """Revert table expressions when inline shift is undone."""
        model = self.sigCfgWidget.model
        df = model.get_dataframe()

        row_idx = self._find_row_by_uid(df, signal_uid)
        if row_idx is None:
            return

        if signal_uid in self._shift_accumulated:
            self._shift_accumulated[signal_uid]['dx'] -= dx
            self._shift_accumulated[signal_uid]['dy'] -= dy

        new_x, new_y = self._build_offset_expressions(
            model, signal_uid,
            self._shift_accumulated.get(signal_uid, {}).get('dx', 0.0),
            self._shift_accumulated.get(signal_uid, {}).get('dy', 0.0)
        )
        self._set_row_xy(model, row_idx, new_x, new_y)

        # Restore original alias when offset goes back to zero
        remaining_dx = self._shift_accumulated.get(signal_uid, {}).get('dx', 0.0)
        remaining_dy = self._shift_accumulated.get(signal_uid, {}).get('dy', 0.0)
        if abs(remaining_dx) < 1e-10 and abs(remaining_dy) < 1e-10:
            if signal_uid in self._shift_original_exprs:
                df = model.get_dataframe()
                if 'Alias' in df.columns:
                    original_alias = self._shift_original_exprs[signal_uid].get('original_alias', '')
                    model.setData(model.createIndex(row_idx, df.columns.get_loc('Alias')), original_alias, 2)
                    self._update_signal_label_and_legend(signal_uid, original_alias)

    def _on_signal_shift_pulse_applied(self, signal_uid: str, pulse_id: str, dx: float, dy: float, source: str):
        """Create or update dedicated row when pulse mode shift is applied."""
        model = self.sigCfgWidget.model
        w = self.canvasStack.currentWidget()

        original_signal, original_plot = self._find_signal_in_canvas(signal_uid)
        if not original_signal:
            return

        df = model.get_dataframe()
        mother_row_idx = self._find_row_by_uid_or_variable(df, signal_uid, original_signal)
        if mother_row_idx is None:
            return

        row_pulse_id = df.at[mother_row_idx, 'PulseId'] if 'PulseId' in df.columns else ''
        global_pulses = self.dataRangeSelector.get_pulse_number()
        var_name = df.at[mother_row_idx, 'Variable'] if 'Variable' in df.columns else ''
        ds_name = df.at[mother_row_idx, 'DS'] if 'DS' in df.columns else ''
        mother_key = (var_name, ds_name)

        # Store original PulseId of mother row before any modifications
        if mother_key not in self._shift_mother_original_pulse_id:
            self._shift_mother_original_pulse_id[mother_key] = row_pulse_id

        # Use the true original for reference
        true_original_pulse_id = self._shift_mother_original_pulse_id[mother_key]

        # Count pulses based on CURRENT mother state, not the original.
        # If previous shifts already extracted pulses, the mother may now have fewer.
        current_mother_pulse_id = df.at[mother_row_idx, 'PulseId'] if 'PulseId' in df.columns else ''
        pulse_key = f"{signal_uid}_{pulse_id}"
        already_tracked = pulse_key in self._shift_original_exprs

        # Validate that tracked shifted row still exists in the table.
        # If the user manually deleted the shifted row, the tracking is stale.
        if already_tracked:
            _trk = self._shift_original_exprs[pulse_key]
            _stored_alias = _trk.get('alias', '')
            _is_inline = _trk.get('inline_mode', False)

            if not _is_inline and _stored_alias:
                df_check = model.get_dataframe()
                if self._find_row_by_alias(df_check, _stored_alias) is None:
                    logger.debug(f"Stale shift tracking for {pulse_key}: "
                                 f"row '{_stored_alias}' no longer exists, cleaning up.")
                    self._cleanup_stale_shift_entry(pulse_key)
                    already_tracked = False
                    # Re-read state since cleanup may have modified mother's PulseId
                    df = model.get_dataframe()
                    mother_row_idx = self._find_row_by_uid_or_variable(
                        df, signal_uid, original_signal)
                    if mother_row_idx is None:
                        return
                    current_mother_pulse_id = (
                        df.at[mother_row_idx, 'PulseId']
                        if 'PulseId' in df.columns else ''
                    )

        if already_tracked and not self._shift_original_exprs[pulse_key].get('inline_mode', False):
            # This pulse already has an active dedicated row, keep using multi-pulse path
            pulse_count = 2  # force multi-pulse path
        else:
            # Count from current mother state to decide inline vs new row
            pulse_count = self._count_active_pulses(current_mother_pulse_id, global_pulses)

        # Single pulse remaining: use inline mode (modify mother row directly)
        if pulse_count <= 1:
            # Register tracking under pulse_key so undo can find it
            if pulse_key not in self._shift_original_exprs:
                self._shift_original_exprs[pulse_key] = {
                    'x': df.at[mother_row_idx, 'x'] if 'x' in df.columns else '',
                    'y': df.at[mother_row_idx, 'y'] if 'y' in df.columns else '',
                    'stack': df.at[mother_row_idx, 'Stack'] if 'Stack' in df.columns else '',
                    'original_label': getattr(original_signal, 'label', '') or getattr(original_signal, 'name', ''),
                    'alias': '',
                    'original_alias': df.at[mother_row_idx, 'Alias'] if 'Alias' in df.columns else '',
                    'mother_pulse_updated': False,
                    'inline_mode': True,
                    'var_name': var_name,
                    'ds_name': ds_name
                }
                self._shift_accumulated[pulse_key] = {'dx': 0.0, 'dy': 0.0}

            self._shift_accumulated[pulse_key]['dx'] += dx
            self._shift_accumulated[pulse_key]['dy'] += dy
            total_dx = self._shift_accumulated[pulse_key]['dx']
            total_dy = self._shift_accumulated[pulse_key]['dy']

            new_x, new_y = self._build_offset_expressions(model, pulse_key, total_dx, total_dy)
            self._set_row_xy(model, mother_row_idx, new_x, new_y)

            # Set alias on the inline row
            df = model.get_dataframe()
            if 'Alias' in df.columns:
                stored_alias = self._shift_original_exprs[pulse_key].get('alias', '')
                if not stored_alias:
                    mother_alias = df.at[mother_row_idx, 'Alias'] if 'Alias' in df.columns else ''
                    stored_alias = self._generate_unique_alias(model, var_name, 'shifted', pulse_id,
                                                               row_alias=mother_alias)
                    self._shift_original_exprs[pulse_key]['alias'] = stored_alias
                model.setData(model.createIndex(mother_row_idx, df.columns.get_loc('Alias')), stored_alias, 2)

            # Update signal label and legend
            stored_alias = self._shift_original_exprs[pulse_key].get('alias', '')
            if stored_alias:
                self._update_signal_label_and_legend(signal_uid, stored_alias)
            return

        # Multiple pulses: create dedicated row
        if pulse_key not in self._shift_original_exprs:
            effective_pulse_id = row_pulse_id
            if not effective_pulse_id:
                if isinstance(global_pulses, list):
                    effective_pulse_id = ','.join(str(p) for p in global_pulses)
                else:
                    effective_pulse_id = str(global_pulses) if global_pulses else ''
            self._shift_original_exprs[pulse_key] = {
                'x': df.at[mother_row_idx, 'x'] if 'x' in df.columns else '',
                'y': df.at[mother_row_idx, 'y'] if 'y' in df.columns else '',
                'stack': df.at[mother_row_idx, 'Stack'] if 'Stack' in df.columns else '',
                'pulse_id': effective_pulse_id,
                'pulse_id_was_empty': not row_pulse_id,
                'original_label': getattr(original_signal, 'label', '') or getattr(original_signal, 'name', ''),
                'alias': '',
                'mother_pulse_updated': False,
                'inline_mode': False,
                'var_name': var_name,
                'ds_name': ds_name
            }
            self._shift_accumulated[pulse_key] = {'dx': 0.0, 'dy': 0.0}

        self._shift_accumulated[pulse_key]['dx'] += dx
        self._shift_accumulated[pulse_key]['dy'] += dy
        total_dx = self._shift_accumulated[pulse_key]['dx']
        total_dy = self._shift_accumulated[pulse_key]['dy']

        new_x, new_y = self._build_offset_expressions(model, pulse_key, total_dx, total_dy)

        stored_alias = self._shift_original_exprs[pulse_key].get('alias', '')
        df = model.get_dataframe()
        existing_row = self._find_row_by_alias(df, stored_alias) if stored_alias else None

        # Update mother row PulseId (keep Stack unchanged)
        if not self._shift_original_exprs[pulse_key].get('mother_pulse_updated', False):
            df = model.get_dataframe()
            mother_row_idx = self._find_row_by_uid_or_variable(df, signal_uid, original_signal)
            if mother_row_idx is not None and 'PulseId' in df.columns:
                # Use current PulseId of mother (may have been modified by previous shifts)
                current_mother_pulse_id = df.at[mother_row_idx, 'PulseId'] if 'PulseId' in df.columns else ''
                # Only use true_original if mother hasn't been modified yet
                if mother_key not in self._shift_mother_original_pulse_id or current_mother_pulse_id == true_original_pulse_id:
                    base_pulse_id = true_original_pulse_id
                else:
                    # Mother has been modified, use current state
                    base_pulse_id = current_mother_pulse_id
                resolved_globals = self._resolve_global_pulses(global_pulses, ds_name)
                remaining_pulses = self._build_remaining_pulse_expr(base_pulse_id, pulse_id, resolved_globals)
                model.setData(model.createIndex(mother_row_idx, df.columns.get_loc('PulseId')), remaining_pulses, 2)
                self._shift_original_exprs[pulse_key]['mother_pulse_updated'] = True

        if not stored_alias:
            mother_alias = df.at[mother_row_idx, 'Alias'] if 'Alias' in df.columns else ''
            stored_alias = self._generate_unique_alias(model, var_name, 'shifted', pulse_id,
                                                       row_alias=mother_alias)
            self._shift_original_exprs[pulse_key]['alias'] = stored_alias

        self._update_signal_label_and_legend(signal_uid, stored_alias)

        if existing_row is not None:
            self._set_row_xy(model, existing_row, new_x, new_y)
        else:
            self._create_shifted_row(model, original_signal, signal_uid, pulse_id,
                                     stored_alias, new_x, new_y, pulse_key)


    def _on_signal_shift_pulse_undone(self, signal_uid: str, pulse_id: str,
                                       previous_dx: float, previous_dy: float):
        """Restore state when pulse mode shift is undone."""
        model = self.sigCfgWidget.model
        w = self.canvasStack.currentWidget()

        pulse_key = f"{signal_uid}_{pulse_id}"
        original_signal, original_plot = self._find_signal_in_canvas(signal_uid)
        tracking = self._shift_original_exprs.get(pulse_key, {})

        # If tracking was already cleaned up (e.g., user manually deleted the shifted row),
        # skip table manipulation — the manual-delete handler already restored state.
        if not tracking:
            self.canvasStack.refreshLinks()
            return

        stored_alias = tracking.get('alias', '')
        is_inline = tracking.get('inline_mode', False)

        if pulse_key in self._shift_accumulated:
            self._shift_accumulated[pulse_key] = {'dx': previous_dx, 'dy': previous_dy}

        is_final_undo = abs(previous_dx) < 1e-10 and abs(previous_dy) < 1e-10

        if is_inline:
            # Inline mode: revert changes on the mother row directly
            df = model.get_dataframe()
            mother_row_idx = self._find_row_by_uid_or_variable(df, signal_uid, original_signal) if original_signal else None

            if is_final_undo:
                # Restore original x/y expressions
                if mother_row_idx is not None:
                    self._set_row_xy(model, mother_row_idx, tracking.get('x', ''), tracking.get('y', ''))
                    # Restore original alias
                    df = model.get_dataframe()
                    if 'Alias' in df.columns:
                        original_alias = tracking.get('original_alias', '')
                        model.setData(model.createIndex(mother_row_idx, df.columns.get_loc('Alias')), original_alias, 2)

                # Clean up mother original pulse id if no other shifts remain
                var_name = tracking.get('var_name', '')
                ds_name = tracking.get('ds_name', '')
                mother_key = (var_name, ds_name)
                if mother_key in self._shift_mother_original_pulse_id:
                    other_active = any(
                        v.get('mother_pulse_updated', False)
                        and v.get('var_name') == var_name
                        and v.get('ds_name') == ds_name
                        for k, v in self._shift_original_exprs.items()
                        if k != pulse_key
                    )
                    if not other_active:
                        del self._shift_mother_original_pulse_id[mother_key]

                if pulse_key in self._shift_original_exprs:
                    self._shift_original_exprs[pulse_key]['mother_pulse_updated'] = False
            else:
                # Partial undo: update expressions with remaining offset
                new_x, new_y = self._build_offset_expressions(model, pulse_key, previous_dx, previous_dy)
                if mother_row_idx is not None:
                    self._set_row_xy(model, mother_row_idx, new_x, new_y)
        else:
            # Multi-pulse mode: dedicated row exists
            if is_final_undo:
                if stored_alias:
                    df = model.get_dataframe()
                    row_to_delete = self._find_row_by_alias(df, stored_alias)
                    if row_to_delete is not None:
                        if hasattr(model, 'aliases') and stored_alias in model.aliases:
                            model.aliases.remove(stored_alias)
                        self._shift_undo_in_progress = True
                        try:
                            model.removeRows(row_to_delete, 1, QModelIndex())
                        finally:
                            self._shift_undo_in_progress = False

                if original_signal:
                    df = model.get_dataframe()
                    mother_row_idx = self._find_row_by_uid_or_variable(df, signal_uid, original_signal)
                    if mother_row_idx is not None and 'PulseId' in df.columns:
                        var_name = tracking.get('var_name', '')
                        ds_name = tracking.get('ds_name', '')
                        mother_key = (var_name, ds_name)

                        # Check if there are other active shifts for this mother
                        other_active_shifts = any(
                            v.get('mother_pulse_updated', False)
                            and v.get('var_name') == var_name
                            and v.get('ds_name') == ds_name
                            for k, v in self._shift_original_exprs.items()
                            if k != pulse_key
                        )

                        if not other_active_shifts and mother_key in self._shift_mother_original_pulse_id:
                            # No other shifts, restore true original
                            true_original = self._shift_mother_original_pulse_id[mother_key]
                            model.setData(model.createIndex(mother_row_idx, df.columns.get_loc('PulseId')), true_original, 2)
                            del self._shift_mother_original_pulse_id[mother_key]
                        else:
                            # Other shifts exist, re-add this pulse to current mother PulseId list
                            current_pulse_id = df.at[mother_row_idx, 'PulseId']
                            restored = self._add_pulse_to_list(current_pulse_id, pulse_id)
                            model.setData(model.createIndex(mother_row_idx, df.columns.get_loc('PulseId')), restored, 2)

                if pulse_key in self._shift_original_exprs:
                    self._shift_original_exprs[pulse_key]['mother_pulse_updated'] = False
            else:
                new_x, new_y = self._build_offset_expressions(model, pulse_key, previous_dx, previous_dy)
                if stored_alias:
                    df = model.get_dataframe()
                    existing_row = self._find_row_by_alias(df, stored_alias)
                    if existing_row is not None:
                        self._set_row_xy(model, existing_row, new_x, new_y)

        # Common: restore label on final undo, rebuild legend always
        if is_final_undo:
            original_label = tracking.get('original_label', '')
            if original_signal and original_label:
                self._update_signal_label_and_legend(signal_uid, original_label)
            # Clean up tracking so future shifts re-evaluate inline vs multi-pulse
            self._shift_original_exprs.pop(pulse_key, None)
            self._shift_accumulated.pop(pulse_key, None)
        elif original_signal:
            # Partial undo: just rebuild legend with current state
            w = self.canvasStack.currentWidget()
            original_signal_ref, original_plot = self._find_signal_in_canvas(signal_uid)
            if w and original_plot:
                impl_plot = w._parser._signal_impl_plot_lut.get(signal_uid)
                if impl_plot:
                    w._parser.rebuild_legend(impl_plot, original_plot)

        self.canvasStack.refreshLinks()

    def _on_signal_shift_requested(self, signal_uid: str, signal_name: str, data_source: str,
                                      pulse_nb: str, dx: float, dy: float, duplicate: bool):
        """Process shift request from DIST dialog."""
        w = self.canvasStack.currentWidget()
        model = self.sigCfgWidget.model

        original_signal, original_plot = self._find_signal_in_canvas(signal_uid)
        if not original_signal:
            return

        if original_signal.envelope:
            logger.warning("Shift is not supported for envelope signals.")
            return

        if duplicate:
            self._handle_dist_duplicate(model, original_signal, signal_uid, dx, dy)
            self.canvasStack.refreshLinks()
            w.check_markers(self.canvas)
            w.stats(self.canvas)
            return

        signal_pulse = getattr(original_signal, 'pulse_nb', None)
        is_pulse_mode = signal_pulse is not None and str(signal_pulse).strip() != ''
        shifted_pulse = str(signal_pulse) if is_pulse_mode else ''

        from iplotlib.core.commands.shift import ShiftCommand
        cmd = ShiftCommand(
            signal=original_signal,
            dx=dx,
            dy=dy,
            parser=w._parser,
            qt_canvas=w,
            is_pulse_isolation=is_pulse_mode,
            pulse_id=shifted_pulse if is_pulse_mode else None,
            source='dist'
        )

        previous_dx = getattr(original_signal, '_drag_shift_dx', 0.0)
        previous_dy = getattr(original_signal, '_drag_shift_dy', 0.0)
        if abs(dx) > 1e-10:
            original_signal._drag_shift_dx = previous_dx + dx
        if abs(dy) > 1e-10:
            original_signal._drag_shift_dy = previous_dy + dy
        w._parser.process_ipl_signal(original_signal)

        impl_plot = w._parser._signal_impl_plot_lut.get(signal_uid)
        if impl_plot and original_plot:
            w._parser.rebuild_legend(impl_plot, original_plot)

        w._parser._hm.done(cmd)
        w.cmdDone.emit(cmd)

        if is_pulse_mode:
            w.signalShiftPulseApplied.emit(signal_uid, shifted_pulse, dx, dy, 'dist')
        else:
            w.signalShiftApplied.emit(signal_uid, dx, dy, 'dist')

        self.canvasStack.refreshLinks()
        w.check_markers(self.canvas)
        w.stats(self.canvas)

    def _handle_dist_duplicate(self, model, original_signal, signal_uid: str, dx: float, dy: float):
        """Create a new shifted row while keeping the original unchanged."""
        df = model.get_dataframe()
        row_idx = self._find_row_by_uid_or_variable(df, signal_uid, original_signal)
        if row_idx is None:
            return

        var_name = df.at[row_idx, 'Variable'] if 'Variable' in df.columns else ''
        original_x = df.at[row_idx, 'x'] if 'x' in df.columns else ''
        original_y = df.at[row_idx, 'y'] if 'y' in df.columns else ''
        original_stack = df.at[row_idx, 'Stack'] if 'Stack' in df.columns else ''

        new_x, new_y = self._build_offset_expressions_from(model, original_x, original_y, dx, dy)
        row_alias = df.at[row_idx, 'Alias'] if 'Alias' in df.columns else ''
        new_alias = self._generate_unique_alias(model, var_name, 'shifted', row_alias=row_alias)

        new_row_idx = row_idx + 1
        model.insertRows(new_row_idx, 1, QModelIndex())
        df = model.get_dataframe()

        for col_idx, col_name in enumerate(df.columns):
            if col_name == 'uid':
                continue
            elif col_name == 'x':
                val = new_x
            elif col_name == 'y':
                val = new_y
            elif col_name == 'Alias':
                val = new_alias
            elif col_name == 'Stack':
                val = original_stack
            elif col_name not in ['Status', 'Output Datatype']:
                val = df.at[row_idx, col_name]
            else:
                continue
            if val is not None:
                model.setData(model.createIndex(new_row_idx, col_idx), val, 2)

    def _find_row_by_uid(self, df, signal_uid: str):
        """Find row index by signal uid."""
        if 'uid' in df.columns:
            matches = df.index[df['uid'] == signal_uid].tolist()
            if matches:
                return matches[0]
        return None

    def _find_signal_in_canvas(self, signal_uid: str):
        """Find signal and its plot by uid. Returns (signal, plot) or (None, None)."""
        for col in self.canvas.plots:
            for plot in col:
                if not plot:
                    continue
                for sigs in plot.signals.values():
                    for sig in sigs:
                        if sig and getattr(sig, 'uid', None) == signal_uid:
                            return sig, plot
        return None, None

    def _find_row_by_uid_or_variable(self, df, signal_uid: str, signal=None):
        """Find row index by uid, falling back to Variable/DS/PulseId match."""
        if 'uid' in df.columns:
            matches = df.index[df['uid'] == signal_uid].tolist()
            if matches:
                return matches[0]
        if signal and 'Variable' in df.columns and 'DS' in df.columns:
            sig_name = getattr(signal, 'name', '')
            sig_ds = getattr(signal, 'data_source', '')
            var_ds_matches = df.index[(df['Variable'] == sig_name) & (df['DS'] == sig_ds)].tolist()

            # If multiple rows match Variable/DS, use pulse_nb to find the correct one
            if len(var_ds_matches) > 1 and 'PulseId' in df.columns:
                sig_pulse = str(getattr(signal, 'pulse_nb', '') or '').strip()
                if sig_pulse:
                    for idx in var_ds_matches:
                        row_pulse_id = str(df.at[idx, 'PulseId'] or '').strip()
                        # Check if the signal's pulse is contained in this row's PulseId
                        if sig_pulse in row_pulse_id.split(',') or sig_pulse == row_pulse_id:
                            return idx
                        # Also check for pulse
                        if any(p.strip().endswith(f'@{sig_pulse}') for p in row_pulse_id.split(',')):
                            return idx

            if var_ds_matches:
                return var_ds_matches[0]
        return None

    def _generate_unique_alias(self, model, var_name: str, prefix: str, pulse_id: str = None,
                              row_alias: str = '') -> str:
        """Generate a unique alias for the shifted signal."""
        df = model.get_dataframe()
        existing = [a for a in df['Alias'].tolist() if a] if 'Alias' in df.columns else []
        display_name = row_alias.strip() if row_alias and row_alias.strip() else (
            var_name if '${' not in var_name else ''
        )
        # Strip existing shifted prefixes
        if display_name:
            display_name = re.sub(r'^(shifted\d*_)+', '', display_name)
            # Strip trailing pulse_id
            if pulse_id and display_name.endswith(f'_{pulse_id}'):
                display_name = display_name[:-len(f'_{pulse_id}')]
        # Include pulse_id in alias when provided (multiple pulses case)
        if pulse_id:
            base_alias = f"{prefix}_{display_name}_{pulse_id}" if display_name else f"{prefix}_{pulse_id}"
        else:
            base_alias = f"{prefix}_{display_name}" if display_name else prefix
        if base_alias not in existing:
            return base_alias
        for i in range(2, 100):
            if pulse_id:
                candidate = f"{prefix}{i}_{display_name}_{pulse_id}" if display_name else f"{prefix}{i}_{pulse_id}"
            else:
                candidate = f"{prefix}{i}_{display_name}" if display_name else f"{prefix}{i}"
            if candidate not in existing:
                return candidate
        return base_alias

    def _count_active_pulses(self, row_pulse_id: str, global_pulses) -> int:
        """Count effective pulses considering +/- syntax and globals."""
        if not row_pulse_id:
            return len(global_pulses) if isinstance(global_pulses, list) else (1 if global_pulses else 0)

        row_pulse_id = str(row_pulse_id).strip()
        if row_pulse_id.startswith('+(') or row_pulse_id.startswith('-('):
            base_count = len(global_pulses) if isinstance(global_pulses, list) else 1
            return base_count + (1 if row_pulse_id.startswith('+') else -1)

        return len([p for p in row_pulse_id.split(',') if p.strip()])

    def _resolve_global_pulses(self, global_pulses, ds_name: str):
        """Resolve relative global pulses (0, -N) to concrete pulses so an
        already-resolved shifted pulse can be matched against them and excluded."""
        model = self.sigCfgWidget.model
        if isinstance(global_pulses, list):
            exprs = [str(p).strip() for p in global_pulses if str(p).strip()]
        elif global_pulses:
            exprs = [str(global_pulses).strip()]
        else:
            return global_pulses
        return [model._resolve_relative_pulse(expr, ds_name, expr) for expr in exprs]

    def _build_remaining_pulse_expr(self, original_pulse_id: str, shifted_pulse: str, global_pulses=None) -> str:
        """Build PulseId expression for non-manipulated pulses.

        When shifting a pulse, the mother row must show only the non-shifted pulses.
        Always returns an explicit list of pulses for clarity and consistency.
        """
        # Helper to check if pulse matches shifted_pulse
        def matches_shifted(p):
            p = str(p).strip()
            return p == shifted_pulse or p.endswith(f'@{shifted_pulse}')

        # Helper to get global pulses as list
        def get_globals_list():
            if not global_pulses:
                return []
            if isinstance(global_pulses, list):
                return [str(p).strip() for p in global_pulses]
            return [str(global_pulses).strip()]

        if not original_pulse_id:
            # Was using globals, expand to explicit list minus the shifted one
            remaining = [p for p in get_globals_list() if not matches_shifted(p)]
            return ','.join(remaining)

        original_pulse_id = str(original_pulse_id).strip()

        # Handle +(...) expression: adding specific pulse to globals
        if original_pulse_id.startswith('+('):
            inner = original_pulse_id[2:-1] if original_pulse_id.endswith(')') else original_pulse_id[2:]
            # Check if the shifted pulse is the one being added
            if matches_shifted(inner):
                # The added pulse is being shifted, mother keeps only globals minus shifted
                remaining = [p for p in get_globals_list() if not matches_shifted(p)]
                return ','.join(remaining)
            # The shifted pulse is from globals - expand to explicit list
            # Result: globals - shifted + inner
            remaining = [p for p in get_globals_list() if not matches_shifted(p)]
            remaining.append(inner)
            return ','.join(remaining)

        # Handle -(...) expression: excluding pulses from globals
        if original_pulse_id.startswith('-('):
            inner = original_pulse_id[2:-1] if original_pulse_id.endswith(')') else original_pulse_id[2:]
            # Expand globals, exclude already excluded and the shifted one
            excluded = set(p.strip() for p in inner.split(','))
            remaining = [p for p in get_globals_list()
                        if not matches_shifted(p) and p not in excluded
                        and not any(p.endswith(f'@{ex}') for ex in excluded)]
            return ','.join(remaining)

        # Handle explicit list of pulses
        pulses = [p.strip() for p in original_pulse_id.split(',')]
        remaining = [p for p in pulses if not matches_shifted(p)]
        return ','.join(remaining)

    def _remove_pulse_from_list(self, pulse_list_str: str, pulse_to_remove: str) -> str:
        """Remove a pulse from a comma-separated list."""
        if not pulse_list_str:
            return ''
        if isinstance(pulse_list_str, list):
            pulses = [str(p).strip() for p in pulse_list_str]
        else:
            pulses = [p.strip() for p in str(pulse_list_str).split(',')]
        pulses = [p for p in pulses if not (p == pulse_to_remove or p.endswith(f'@{pulse_to_remove}'))]
        return ','.join(pulses)

    def _add_pulse_to_list(self, pulse_list_str: str, pulse_to_add: str) -> str:
        """Add a pulse to a comma-separated list, maintaining order."""
        if not pulse_list_str:
            return pulse_to_add
        if isinstance(pulse_list_str, list):
            pulses = [str(p).strip() for p in pulse_list_str]
        else:
            pulses = [p.strip() for p in str(pulse_list_str).split(',') if p.strip()]

        # Check if already in list
        if pulse_to_add in pulses:
            return ','.join(pulses)

        # Add and sort to maintain consistent ordering
        pulses.append(pulse_to_add)
        return ','.join(pulses)

    def _find_row_by_alias(self, df, alias: str):
        """Find row index by alias."""
        if not alias or 'Alias' not in df.columns:
            return None
        for idx, a in df['Alias'].items():
            if a == alias:
                return idx
        return None

    def _cleanup_stale_shift_entry(self, pulse_key: str):
        """Remove a stale tracking entry whose shifted row no longer exists.

        Cleans up _shift_original_exprs, _shift_accumulated, and
        _shift_mother_original_pulse_id when appropriate.
        """
        tracking = self._shift_original_exprs.get(pulse_key)
        if not tracking:
            return

        var_name = tracking.get('var_name', '')
        ds_name = tracking.get('ds_name', '')
        mother_key = (var_name, ds_name)

        # Check if other active shifts exist for the same mother signal
        other_active = any(
            v.get('mother_pulse_updated', False)
            and v.get('var_name') == var_name
            and v.get('ds_name') == ds_name
            for k, v in self._shift_original_exprs.items()
            if k != pulse_key
        )

        # Clean up mother original pulse tracking if this was the last shift
        if not other_active and mother_key in self._shift_mother_original_pulse_id:
            del self._shift_mother_original_pulse_id[mother_key]

        self._shift_original_exprs.pop(pulse_key, None)
        self._shift_accumulated.pop(pulse_key, None)

    def _build_offset_expressions(self, model, key: str, total_dx: float, total_dy: float):
        """Build x/y expressions with the accumulated offset (reads originals from tracking)."""
        tracking = self._shift_original_exprs.get(key)
        if tracking is None:
            return '', ''
        original_x = tracking.get('x', '')
        original_y = tracking.get('y', '')
        return self._build_offset_expressions_from(model, original_x, original_y, total_dx, total_dy)

    def _create_shifted_row(self, model, signal, signal_uid: str, pulse_id: str,
                            alias: str, new_x: str, new_y: str, pulse_key: str):
        """Insert a new table row for the shifted signal."""
        df = model.get_dataframe()
        mother_row_idx = self._find_row_by_uid_or_variable(df, signal_uid, signal)
        if mother_row_idx is None:
            return

        # Read Stack directly from the current mother row (most up-to-date)
        mother_stack = df.at[mother_row_idx, 'Stack'] if 'Stack' in df.columns else ''
        # Fall back to tracking dict if mother has empty stack but tracking stored one
        original_stack = mother_stack if mother_stack else self._shift_original_exprs.get(pulse_key, {}).get('stack', '')
        new_row_idx = mother_row_idx + 1
        model.insertRows(new_row_idx, 1, QModelIndex())

        df = model.get_dataframe()
        for col_idx, col_name in enumerate(df.columns):
            if col_name == 'uid':
                continue
            elif col_name == 'x':
                val = new_x
            elif col_name == 'y':
                val = new_y
            elif col_name == 'Alias':
                val = alias
            elif col_name == 'PulseId':
                val = pulse_id
            elif col_name == 'Stack':
                val = original_stack
            elif col_name not in ['Status', 'Output Datatype']:
                val = df.at[mother_row_idx, col_name]
            else:
                continue
            if val is not None:
                model.setData(model.createIndex(new_row_idx, col_idx), val, 2)

    def _on_rows_about_to_be_removed(self, parent, first: int, last: int):
        """Handle rows about to be removed from the signal table.

        Detects if any removed rows are tracked shifted-signal rows.
        If so, cleans up tracking and restores the mother row's PulseId.

        Fires from beginRemoveRows(), BEFORE rows are actually deleted,
        so row data is still readable.
        """
        if not self._shift_original_exprs:
            return  # No active tracking, nothing to do
        if self._shift_undo_in_progress:
            return  # Undo handler manages cleanup itself

        model = self.sigCfgWidget.model
        df = model.get_dataframe()

        if df.empty:
            return

        # Collect aliases of rows being removed
        removed_aliases = set()
        for row_idx in range(first, last + 1):
            if row_idx < len(df) and 'Alias' in df.columns:
                alias = df.at[row_idx, 'Alias']
                if alias:
                    removed_aliases.add(alias)

        if not removed_aliases:
            return

        # Find which tracked shift entries correspond to removed rows
        stale_keys = []
        for pulse_key, tracking in self._shift_original_exprs.items():
            stored_alias = tracking.get('alias', '')
            is_inline = tracking.get('inline_mode', False)
            if not is_inline and stored_alias and stored_alias in removed_aliases:
                stale_keys.append(pulse_key)

        if not stale_keys:
            return

        # Process each stale entry: restore mother PulseId where appropriate
        for pulse_key in stale_keys:
            tracking = self._shift_original_exprs[pulse_key]
            var_name = tracking.get('var_name', '')
            ds_name = tracking.get('ds_name', '')
            mother_key = (var_name, ds_name)
            was_mother_updated = tracking.get('mother_pulse_updated', False)

            # Read the shifted pulse_id from the row being deleted
            shifted_pulse_id = None
            stored_alias = tracking.get('alias', '')
            if stored_alias:
                shifted_row = self._find_row_by_alias(df, stored_alias)
                if shifted_row is not None and 'PulseId' in df.columns:
                    shifted_pulse_id = str(df.at[shifted_row, 'PulseId']).strip()

            # Count other active (non-stale) shifts for the same mother
            other_active_shifts = [
                k for k, v in self._shift_original_exprs.items()
                if k != pulse_key
                and k not in stale_keys
                and v.get('mother_pulse_updated', False)
                and v.get('var_name') == var_name
                and v.get('ds_name') == ds_name
            ]

            if was_mother_updated and mother_key in self._shift_mother_original_pulse_id:
                # Find the mother row by Variable+DS, excluding rows being deleted
                mother_row_idx = None
                if 'Variable' in df.columns and 'DS' in df.columns:
                    candidates = df.index[
                        (df['Variable'] == var_name) & (df['DS'] == ds_name)
                    ].tolist()
                    candidates = [i for i in candidates if i < first or i > last]
                    if candidates:
                        mother_row_idx = candidates[0]

                if mother_row_idx is not None and 'PulseId' in df.columns:
                    if not other_active_shifts:
                        # Last shift being removed: restore true original PulseId
                        true_original = self._shift_mother_original_pulse_id[mother_key]
                        model.setData(
                            model.createIndex(
                                mother_row_idx,
                                df.columns.get_loc('PulseId')),
                            true_original, 2)
                    elif shifted_pulse_id:
                        # Other shifts remain: re-add just this pulse
                        current_pulse_id = df.at[mother_row_idx, 'PulseId']
                        restored = self._add_pulse_to_list(
                            current_pulse_id, shifted_pulse_id)
                        model.setData(
                            model.createIndex(
                                mother_row_idx,
                                df.columns.get_loc('PulseId')),
                            restored, 2)

            # Clean up tracking
            if not other_active_shifts and mother_key in self._shift_mother_original_pulse_id:
                del self._shift_mother_original_pulse_id[mother_key]

            self._shift_original_exprs.pop(pulse_key, None)
            self._shift_accumulated.pop(pulse_key, None)
