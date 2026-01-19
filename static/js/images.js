// Image attachment handling

import { state } from './state.js';
import { AIDER_API } from './config.js';

let imageDropzoneEl = null;
let imageInputEl = null;
let imageListEl = null;

export async function getResizedImageBase64(dataUrl, maxSize = 1024) {
  if (!dataUrl) return '';
  const originalBase64 = dataUrl.split(',')[1] || '';
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      const maxDimension = Math.max(img.width, img.height);
      if (!maxDimension || maxDimension <= maxSize) {
        resolve(originalBase64);
        return;
      }

      const scale = maxSize / maxDimension;
      const targetWidth = Math.max(1, Math.round(img.width * scale));
      const targetHeight = Math.max(1, Math.round(img.height * scale));
      const canvas = document.createElement('canvas');
      canvas.width = targetWidth;
      canvas.height = targetHeight;
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        resolve(originalBase64);
        return;
      }
      ctx.drawImage(img, 0, 0, targetWidth, targetHeight);

      const match = dataUrl.match(/^data:(image\/[a-zA-Z0-9.+-]+);base64,/);
      const inputMime = match ? match[1].toLowerCase() : 'image/jpeg';
      let outputMime = inputMime;
      if (!['image/png', 'image/jpeg', 'image/webp'].includes(outputMime)) {
        outputMime = 'image/jpeg';
      }
      const resizedDataUrl = outputMime === 'image/jpeg'
        ? canvas.toDataURL(outputMime, 0.85)
        : canvas.toDataURL(outputMime);
      const resizedBase64 = resizedDataUrl.split(',')[1] || '';
      resolve(resizedBase64 || originalBase64);
    };
    img.onerror = () => resolve(originalBase64);
    img.src = dataUrl;
  });
}

export function initImageElements() {
  imageDropzoneEl = document.getElementById('image-dropzone');
  imageInputEl = document.getElementById('image-input');
  imageListEl = document.getElementById('image-list');
}

export function setupImageDropzone() {
  if (!imageDropzoneEl || !imageInputEl) {
    return;
  }
  imageDropzoneEl.addEventListener('dragover', (event) => {
    event.preventDefault();
    imageDropzoneEl.classList.add('dragover');
  });
  imageDropzoneEl.addEventListener('dragleave', () => {
    imageDropzoneEl.classList.remove('dragover');
  });
  imageDropzoneEl.addEventListener('drop', (event) => {
    event.preventDefault();
    imageDropzoneEl.classList.remove('dragover');
    const files = Array.from(event.dataTransfer.files || []);
    handleImageFiles(files);
  });
  imageInputEl.addEventListener('change', (event) => {
    const files = Array.from(event.target.files || []);
    handleImageFiles(files);
    imageInputEl.value = '';
  });
}

export function openImagePicker() {
  if (imageInputEl) {
    imageInputEl.click();
  }
}

export function handleImageFiles(files) {
  const images = files.filter(file => file.type.startsWith('image/'));
  images.forEach(file => {
    const reader = new FileReader();
    reader.onload = () => {
      state.attachedImages.push({
        name: file.name,
        dataUrl: reader.result
      });
      renderImageList();
    };
    reader.readAsDataURL(file);
  });
}

export function renderImageList() {
  if (!imageListEl) return;
  if (state.attachedImages.length === 0) {
    imageListEl.innerHTML = '';
    return;
  }
  imageListEl.innerHTML = state.attachedImages.map((img, idx) => `
    <span class="image-chip">
      ${img.name}
      <button onclick="removeImage(${idx})">×</button>
    </span>
  `).join('');
}

export function removeImage(index) {
  state.attachedImages.splice(index, 1);
  renderImageList();
}

export function clearImages() {
  state.attachedImages = [];
  renderImageList();
}

export async function describeImages(images) {
  const results = [];
  for (const img of images) {
    const base64 = await getResizedImageBase64(img.dataUrl || '', 1024);
    if (!base64) {
      results.push(`[Image: ${img.name}]\nDescription unavailable (invalid data).`);
      continue;
    }
    try {
      const payload = {
        filename: img.name,
        data: base64,
        compact: true
      };
      if (state.visionModel) {
        payload.model = state.visionModel;
      }
      const res = await fetch(`${AIDER_API}/api/vision/describe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (res.ok && data.success && data.description) {
        results.push(`[Image: ${img.name}]\n${data.description}`);
      } else {
        results.push(`[Image: ${img.name}]\nDescription unavailable (${data.error || 'vision model not configured'}).`);
      }
    } catch (err) {
      results.push(`[Image: ${img.name}]\nDescription unavailable (${err.message}).`);
    }
  }
  return results;
}
