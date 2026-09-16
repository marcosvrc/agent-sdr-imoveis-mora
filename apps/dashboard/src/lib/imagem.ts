/** Lê um arquivo de imagem e devolve um data URL JPEG quadrado (recorte central) de `lado` px — leve o bastante para ir no JSON. */
export async function redimensionarFoto(arquivo: File, lado = 256, qualidade = 0.85): Promise<string> {
  if (!/^image\/(png|jpeg|webp|heic|heif)$/.test(arquivo.type) && !arquivo.type.startsWith("image/")) throw new Error("Escolha um arquivo de imagem (PNG, JPEG ou WebP).");
  const bitmap = await createImageBitmap(arquivo).catch(() => { throw new Error("Não consegui ler essa imagem. Tente PNG ou JPEG."); });
  const canvas = document.createElement("canvas"); canvas.width = lado; canvas.height = lado;
  const ctx = canvas.getContext("2d")!;
  const m = Math.min(bitmap.width, bitmap.height);
  ctx.drawImage(bitmap, (bitmap.width - m) / 2, (bitmap.height - m) / 2, m, m, 0, 0, lado, lado);
  bitmap.close?.();
  const url = canvas.toDataURL("image/jpeg", qualidade);
  if (url.length > 300_000) throw new Error("Imagem grande demais mesmo após reduzir.");
  return url;
}

/** Reduz uma foto mantendo a proporção (lado maior = `max` px) e devolve JPEG em data URL. */
export async function redimensionarImagem(arquivo: File, max = 1280, qualidade = 0.82): Promise<string> {
  if (!arquivo.type.startsWith("image/")) throw new Error(`${arquivo.name}: não é uma imagem.`);
  const bitmap = await createImageBitmap(arquivo).catch(() => { throw new Error(`${arquivo.name}: não consegui ler. Tente PNG ou JPEG.`); });
  const esc = Math.min(1, max / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas"); canvas.width = Math.round(bitmap.width * esc); canvas.height = Math.round(bitmap.height * esc);
  canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close?.();
  const url = canvas.toDataURL("image/jpeg", qualidade);
  if (url.length > 1_400_000) throw new Error(`${arquivo.name}: ficou grande demais mesmo reduzida.`);
  return url;
}
