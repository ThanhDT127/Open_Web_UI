// Prices and Cost Comparison Tab logic
import { mwFetch, updateStatus } from './utils.js';

let _pricesCache = {};
let _editingModelName = null; // null = create mode, string = edit mode

export async function loadPrices() {
    const tbody = document.getElementById('pricesTable');
    try {
        const res = await mwFetch('/v1/_mw/admin/prices');
        if (!res || !res.ok) {
            tbody.innerHTML = '<tr><td colspan="6" class="error-msg">Không thể tải bảng giá</td></tr>';
            return;
        }

        const data = await res.json();
        _pricesCache = data || {};

        renderPricingTable();
        recalcComparison();
    } catch (err) {
        console.error('Failed to load prices:', err);
        tbody.innerHTML = '<tr><td colspan="6" class="error-msg">Lỗi: ' + err.message + '</td></tr>';
    }
}

export function renderPricingTable() {
    const tbody = document.getElementById('pricesTable');
    const totalEl = document.getElementById('totalPricesCount');
    
    // Filter out metadata schema key
    const modelKeys = Object.keys(_pricesCache).filter(key => key !== '_schema');
    if (totalEl) totalEl.textContent = modelKeys.length;

    if (modelKeys.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="no-data">Không có cấu hình giá nào</td></tr>';
        return;
    }

    tbody.innerHTML = modelKeys.map(model => {
        const p = _pricesCache[model] || {};
        const inputCost = p.input_per_1m !== undefined ? `$${p.input_per_1m.toFixed(4)}` : 'n/a';
        const outputCost = p.output_per_1m !== undefined ? `$${p.output_per_1m.toFixed(4)}` : 'n/a';
        
        let imageCost = 'n/a';
        if (p.per_image_usd !== undefined) {
            if (typeof p.per_image_usd === 'object') {
                imageCost = 'Dạng phân giải (Dict)';
            } else {
                imageCost = `$${p.per_image_usd.toFixed(4)}`;
            }
        }
        
        const notes = p.notes || '';
        const modelId = encodeURIComponent(model);

        return `<tr>
            <td class="user-id"><code>${model}</code></td>
            <td>${inputCost}</td>
            <td>${outputCost}</td>
            <td>${imageCost}</td>
            <td style="opacity: 0.8; font-size: 13px;">${notes}</td>
            <td class="actions-cell" style="text-align: right;">
                <button class="btn-icon btn-edit" title="Sửa" onclick="window.dashboardAPI.showEditPriceModal('${modelId}')">✏️</button>
                <button class="btn-icon btn-delete" title="Xóa" onclick="window.dashboardAPI.deletePrice('${modelId}')">🗑️</button>
            </td>
        </tr>`;
    }).join('');
}

export function recalcComparison() {
    const simInput = parseFloat(document.getElementById('simInputTokens').value) || 0;
    const simOutput = parseFloat(document.getElementById('simOutputTokens').value) || 0;
    const container = document.getElementById('comparisonList');

    const modelKeys = Object.keys(_pricesCache).filter(key => key !== '_schema');
    
    // Filter and calculate cost
    const simulatedList = [];
    modelKeys.forEach(model => {
        const p = _pricesCache[model] || {};
        // Only compare text models (must have either input_per_1m or output_per_1m defined)
        if (p.input_per_1m !== undefined || p.output_per_1m !== undefined) {
            const inputRate = p.input_per_1m || 0;
            const outputRate = p.output_per_1m || 0;
            const simulatedCost = (simInput * inputRate / 1000000) + (simOutput * outputRate / 1000000);
            simulatedList.push({
                model,
                inputRate,
                outputRate,
                simulatedCost
            });
        }
    });

    if (simulatedList.length === 0) {
        container.innerHTML = '<div style="color: #94a3b8; font-size: 14px;">Không có model text nào để so sánh</div>';
        return;
    }

    // Sort by cost ascending
    simulatedList.sort((a, b) => a.simulatedCost - b.simulatedCost);

    // Find the max cost to set 100% width reference
    const maxCost = Math.max(...simulatedList.map(item => item.simulatedCost));
    
    container.innerHTML = simulatedList.map(item => {
        const costStr = item.simulatedCost >= 0.01 
            ? `$${item.simulatedCost.toFixed(4)}` 
            : `$${item.simulatedCost.toFixed(6)}`;
            
        // Calculate width percent (min 1% for visibility, max 100%)
        const pct = maxCost > 0 ? Math.max(1, (item.simulatedCost / maxCost) * 100) : 0;
        
        // Dynamic bar color based on cost percent relative to cheapest/most expensive
        const barColor = pct >= 80 ? '#ef4444' : (pct >= 40 ? '#f59e0b' : '#10b981');

        return `
            <div style="display: flex; align-items: center; gap: 15px; font-size: 14px;">
                <div style="width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500;">
                    <code>${item.model}</code>
                </div>
                <div style="flex: 1; background: #1e293b; height: 24px; border-radius: 4px; overflow: hidden; display: flex; align-items: center; position: relative; border: 1px solid #334155;">
                    <div style="width: ${pct}%; background: ${barColor}; height: 100%; transition: width 0.3s ease;"></div>
                    <span style="position: absolute; left: 10px; font-size: 12px; font-weight: bold; color: #fff; text-shadow: 0 1px 2px rgba(0,0,0,0.8);">
                        ${costStr}
                    </span>
                </div>
                <div style="width: 140px; text-align: right; font-size: 12px; color: #94a3b8;">
                    In: $${item.inputRate.toFixed(2)} | Out: $${item.outputRate.toFixed(2)}
                </div>
            </div>
        `;
    }).join('');
}

export function resetSimulator() {
    document.getElementById('simInputTokens').value = '10000';
    document.getElementById('simOutputTokens').value = '2000';
    recalcComparison();
}

export function showAddPriceModal() {
    _editingModelName = null;
    document.getElementById('priceModalTitle').textContent = '➕ Thêm Bảng Giá Model';
    document.getElementById('modalPriceModelName').value = '';
    document.getElementById('modalPriceModelName').disabled = false;
    document.getElementById('modalPriceInput').value = '0';
    document.getElementById('modalPriceOutput').value = '0';
    document.getElementById('modalPriceImage').value = '';
    document.getElementById('modalPriceNotes').value = '';
    document.getElementById('priceModal').style.display = 'flex';
}

export function showEditPriceModal(modelName) {
    modelName = decodeURIComponent(modelName);
    const p = _pricesCache[modelName];
    if (!p) { alert('Model không tồn tại trong cache'); return; }

    _editingModelName = modelName;
    document.getElementById('priceModalTitle').textContent = `✏️ Sửa Bảng Giá: ${modelName}`;
    document.getElementById('modalPriceModelName').value = modelName;
    document.getElementById('modalPriceModelName').disabled = true;
    document.getElementById('modalPriceInput').value = p.input_per_1m || 0;
    document.getElementById('modalPriceOutput').value = p.output_per_1m || 0;
    document.getElementById('modalPriceImage').value = p.per_image_usd !== undefined ? p.per_image_usd : '';
    document.getElementById('modalPriceNotes').value = p.notes || '';
    document.getElementById('priceModal').style.display = 'flex';
}

export function closePriceModal() {
    document.getElementById('priceModal').style.display = 'none';
    _editingModelName = null;
}

export async function savePrice() {
    const saveBtn = document.getElementById('modalPriceSaveBtn');
    const originalText = saveBtn.textContent;
    saveBtn.textContent = 'Đang lưu...';
    saveBtn.disabled = true;

    try {
        const modelName = document.getElementById('modalPriceModelName').value.trim();
        if (!modelName) { alert('Tên model không được để trống'); return; }

        const pricing = {
            input_per_1m: parseFloat(document.getElementById('modalPriceInput').value) || 0,
            output_per_1m: parseFloat(document.getElementById('modalPriceOutput').value) || 0,
        };

        const imgVal = document.getElementById('modalPriceImage').value.trim();
        if (imgVal !== '') {
            pricing.per_image_usd = parseFloat(imgVal) || 0;
        }

        const notesVal = document.getElementById('modalPriceNotes').value.trim();
        if (notesVal !== '') {
            pricing.notes = notesVal;
        }

        const res = await mwFetch('/v1/_mw/admin/prices', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model_name: modelName,
                pricing: pricing
            })
        });

        if (!res || !res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Lưu thất bại');
        }

        updateStatus('ok', `Bảng giá model ${modelName} đã được cập nhật ✓`);
        closePriceModal();
        await loadPrices();
    } catch (err) {
        alert('Lỗi: ' + err.message);
        console.error('Save price error:', err);
    } finally {
        saveBtn.textContent = originalText;
        saveBtn.disabled = false;
    }
}

export async function deletePrice(modelName) {
    modelName = decodeURIComponent(modelName);
    if (!confirm(`⚠️ Bạn có chắc chắn muốn XÓA cấu hình giá cho model "${modelName}"?\n\nHành động này không thể hoàn tác.`)) return;

    try {
        const res = await mwFetch(`/v1/_mw/admin/prices/${encodeURIComponent(modelName)}`, {
            method: 'DELETE'
        });

        if (!res || !res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Xóa thất bại');
        }

        updateStatus('ok', `Bảng giá model ${modelName} đã được xóa ✓`);
        await loadPrices();
    } catch (err) {
        alert('Lỗi xóa: ' + err.message);
    }
}
