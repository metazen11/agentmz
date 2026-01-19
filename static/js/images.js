// Image attachment handling

import { state } from './state.js';
import { AIDER_API } from './config.js';

let imageDropzoneEl = null;
let imageInputEl = null;
let imageListEl = null;

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
    const base64 = (img.dataUrl || '').split(',')[1] || '';
    if (!base64) {
      results.push(`[Image: ${img.name}]\nDescription unavailable (invalid data).`);
      continue;
    }
    try {
      const res = await fetch(`${AIDER_API}/api/vision/describe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: img.name,
          data: base64,
          compact: true
        })
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
