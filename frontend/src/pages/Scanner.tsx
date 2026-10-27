import { Check, ImagePlus, Pencil, RotateCcw, ScanLine, Trash2, UploadCloud, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { API_BASE, api } from "../api";
import type { Detection, Scan } from "../types";
import { Button, Card, Empty, Loading, Notice, PageIntro } from "../components/Ui";

const imageSrc = (path?: string | null) => path ? (path.startsWith("http") ? path : `${API_BASE}${path}`) : "";

async function rotateImage(file: File, degrees: number): Promise<File> {
  if (degrees % 360 === 0) return file;
  const source = await createImageBitmap(file);
  const quarterTurn = Math.abs(degrees) % 180 === 90;
  const canvas = document.createElement("canvas");
  canvas.width = quarterTurn ? source.height : source.width;
  canvas.height = quarterTurn ? source.width : source.height;
  const context = canvas.getContext("2d");
  if (!context) return file;
  context.translate(canvas.width / 2, canvas.height / 2);
  context.rotate((degrees * Math.PI) / 180);
  context.drawImage(source, -source.width / 2, -source.height / 2);
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.92));
  return blob ? new File([blob], file.name.replace(/\.[^.]+$/, "") + "-rotated.jpg", { type: "image/jpeg" }) : file;
}

function FilePreview({ file }: { file: File }) {
  const [imageUrl, setImageUrl] = useState("");
  useEffect(() => {
    const url = URL.createObjectURL(file);
    setImageUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  return imageUrl ? <img src={imageUrl} alt={file.name} className="aspect-[4/3] w-full object-cover" /> : null;
}

export function Scanner() {
  const picker = useRef<HTMLInputElement>(null);
  const camera = useRef<HTMLInputElement>(null);
  const morePicker = useRef<HTMLInputElement>(null);
  const [scan, setScan] = useState<Scan | null>(null);
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [rotation, setRotation] = useState(0);
  const [addingPhotos, setAddingPhotos] = useState(false);
  const [fileName, setFileName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [analysisConsent, setAnalysisConsent] = useState(false);

  const chooseFiles = (files: FileList | null, addToScan = false) => {
    const valid = Array.from(files ?? []).filter((file) => /image\/(jpeg|png|webp)/.test(file.type));
    if (!valid.length) { setError("Choose JPG, JPEG, PNG, or WebP images."); return; }
    setPendingFiles(valid);
    setAddingPhotos(addToScan);
    setRotation(0);
    setAnalysisConsent(false);
    setError("");
  };

  async function startAnalysis() {
    if (!pendingFiles.length) return;
    setBusy(true);
    setError("");
    try {
      const prepared = await Promise.all(pendingFiles.map((file) => rotateImage(file, rotation)));
      let result: Scan;
      if (addingPhotos && scan) {
        result = scan;
        for (const file of prepared) result = await api.addScanPhoto(scan.id, file);
      } else {
        result = await api.analyze(prepared[0]);
        for (const file of prepared.slice(1)) result = await api.addScanPhoto(result.id, file);
      }
      setScan(result);
      setSelected(result.detections.filter((item) => !item.rejected).map((item) => item.id));
      setFileName(prepared.map((file) => file.name).join(", "));
      setPendingFiles([]);
      setAddingPhotos(false);
      setAnalysisConsent(false);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!scan || selected.length === 0) return;
    setBusy(true);
    try {
      await api.confirm(scan.id, selected);
      setScan({ ...scan, status: "SAVED", detections: scan.detections.map((detection) => selected.includes(detection.id) ? { ...detection, confirmed: true } : detection) });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const toggle = (id: string) => setSelected((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id]);
  const reject = async (detection: Detection) => {
    if (!scan) return;
    try {
      const updated = await api.updateDetection(scan.id, detection.id, { rejected: true });
      setScan({ ...scan, detections: scan.detections.map((item) => item.id === updated.id ? updated : item) });
      setSelected((current) => current.filter((id) => id !== detection.id));
    } catch (err) { setError((err as Error).message); }
  };

  return <>
    <PageIntro eyebrow="Smart bundle scanner" title="Turn a clothing pile into a real wardrobe." description="Use your phone camera, select several photos, rotate a sideways image, review visible evidence, and confirm only the garments you want StyleMate to use." action={<div className="flex flex-wrap gap-2"><Button variant="secondary" onClick={() => camera.current?.click()}><ScanLine size={17} />Camera</Button><Button variant="secondary" onClick={() => picker.current?.click()}><UploadCloud size={17} />Gallery</Button></div>} />
    {error && <Notice tone="error">{error}</Notice>}
    <input ref={camera} type="file" accept="image/jpeg,image/png,image/webp" capture="environment" className="hidden" onChange={(event) => chooseFiles(event.target.files)} />
    <input ref={picker} type="file" accept="image/jpeg,image/png,image/webp" multiple className="hidden" onChange={(event) => chooseFiles(event.target.files)} />
    <input ref={morePicker} type="file" accept="image/jpeg,image/png,image/webp" multiple className="hidden" onChange={(event) => chooseFiles(event.target.files, true)} />

    {!scan && !busy && !pendingFiles.length && <Card className="border-dashed p-3"><button onClick={() => picker.current?.click()} className="focus-ring flex min-h-80 w-full flex-col items-center justify-center rounded-3xl border-2 border-dashed border-violet-200 bg-violet-50/40 px-6 text-center hover:bg-violet-50"><span className="grid h-16 w-16 place-items-center rounded-3xl bg-white text-violet-600 shadow-sm"><ScanLine size={28} /></span><span className="mt-5 text-lg font-bold text-slate-900">Drop a bundle photo here</span><span className="mt-2 max-w-md text-sm leading-6 text-slate-500">JPG, JPEG, PNG, or WebP up to 10 MB each. Multiple gallery photos can be analyzed in one session.</span><span className="mt-5 rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white">Select images</span></button></Card>}

    {pendingFiles.length > 0 && !busy && <Card className="mb-6"><div className="flex items-start justify-between gap-4"><div><p className="text-xs font-bold uppercase tracking-wider text-violet-600">Photo review</p><h3 className="mt-1 text-xl font-bold text-slate-950">Ready to analyze {pendingFiles.length} photo{pendingFiles.length === 1 ? "" : "s"}</h3><p className="mt-2 text-sm text-slate-500">Rotate a sideways photo before upload. The backend will still validate the file signature, dimensions, and decoded pixels.</p></div><button onClick={() => { setPendingFiles([]); setAnalysisConsent(false); }} className="rounded-xl p-2 text-slate-400 hover:bg-slate-100" aria-label="Clear selected photos"><X size={18} /></button></div><div className="mt-5 grid gap-4 sm:grid-cols-3">{pendingFiles.map((file) => <div key={`${file.name}-${file.lastModified}`} className="overflow-hidden rounded-2xl border border-slate-200"><FilePreview file={file} /><p className="truncate p-3 text-xs font-semibold text-slate-600">{file.name}</p></div>)}</div><label className="mt-5 flex items-start gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-600"><input checked={analysisConsent} className="mt-1" onChange={(event) => setAnalysisConsent(event.target.checked)} type="checkbox" /><span>I agree to upload these photos to my StyleMate account storage (private in production) and send them to the configured AI provider to identify visible garments.</span></label><div className="mt-5 flex flex-wrap items-center gap-3"><Button variant="secondary" onClick={() => setRotation((current) => (current + 90) % 360)}><RotateCcw size={16} />Rotate {rotation ? `${rotation}°` : "photo"}</Button><Button disabled={!analysisConsent} onClick={startAnalysis}><ScanLine size={16} />{addingPhotos ? "Analyze extra photos" : "Analyze bundle"}</Button></div></Card>}

    {busy && <Card><Loading label="Analyzing visible garments…" /><p className="mt-4 text-sm leading-6 text-slate-500">The configured AI provider is being called. Hidden garments are never inferred.</p></Card>}
    {scan && !busy && !pendingFiles.length && <div className="grid gap-6 xl:grid-cols-[.85fr_1.15fr]"><Card><div className="flex items-center justify-between"><div><p className="text-xs font-bold uppercase tracking-wider text-violet-600">Source image</p><h3 className="mt-1 truncate font-bold text-slate-900">{fileName || "Bundle photo"}</h3></div><span className={`rounded-full px-3 py-1 text-xs font-bold ${scan.status === "SAVED" ? "bg-emerald-100 text-emerald-700" : scan.needs_more_photos ? "bg-amber-100 text-amber-700" : "bg-violet-100 text-violet-700"}`}>{scan.status.replace(/_/g, " ")}</span></div><div className="mt-5 overflow-hidden rounded-2xl bg-slate-100"><img src={imageSrc(scan.original_image_url)} alt="Uploaded clothing bundle" className="max-h-[560px] w-full object-contain" /></div><div className="mt-5 flex flex-wrap gap-3"><Button variant="secondary" onClick={() => { setScan(null); setFileName(""); }}><RotateCcw size={16} />Retake / new scan</Button><Button variant="secondary" onClick={() => morePicker.current?.click()}><ImagePlus size={16} />Add photos</Button></div>{scan.needs_more_photos && <Notice tone="info">Some items are occluded or uncertain. Add a photo with those pieces separated, then review the new detections.</Notice>}</Card><Card><div className="flex items-end justify-between gap-4"><div><p className="text-xs font-bold uppercase tracking-wider text-violet-600">Detection review</p><h3 className="mt-1 text-xl font-bold text-slate-950">What StyleMate can see</h3></div><Button onClick={confirm} disabled={selected.length === 0 || scan.status === "SAVED"}><Check size={17} />Confirm {selected.length} pieces</Button></div>{scan.detections.length === 0 ? <div className="mt-6"><Empty title="No reliable garments found" description="Try a brighter photo with the pieces separated. No wardrobe items were fabricated or saved." /></div> : <div className="mt-6 grid gap-4 sm:grid-cols-2">{scan.detections.map((detection) => <DetectionCard key={detection.id} detection={detection} selected={selected.includes(detection.id)} disabled={scan.status === "SAVED"} onToggle={() => toggle(detection.id)} onReject={() => reject(detection)} />)}</div>}</Card></div>}
  </>;
}

function DetectionCard({ detection, selected, disabled, onToggle, onReject }: { detection: Detection; selected: boolean; disabled: boolean; onToggle: () => void; onReject: () => void }) {
  return <div className={`overflow-hidden rounded-2xl border transition ${selected ? "border-violet-500 ring-2 ring-violet-100" : "border-slate-200"}`}><button disabled={disabled || detection.rejected} onClick={onToggle} className="focus-ring block w-full text-left"><div className="relative aspect-[4/3] bg-slate-100">{detection.image_url ? <img src={imageSrc(detection.image_url)} alt={`${detection.category} preview`} className="h-full w-full object-cover" /> : <div className="grid h-full place-items-center text-xs text-slate-400">No crop available</div>}<span className={`absolute right-3 top-3 grid h-7 w-7 place-items-center rounded-full ${selected ? "bg-violet-600 text-white" : "bg-white/90 text-transparent"}`}><Check size={15} /></span></div><div className="p-4"><div className="flex items-start justify-between gap-2"><p className="font-bold capitalize text-slate-900">{detection.category}</p><span className="text-xs font-semibold text-slate-400">{Math.round(detection.confidence * 100)}%</span></div><p className="mt-1 text-sm text-slate-500">{detection.primary_color || "Colour unknown"}{detection.pattern ? ` · ${detection.pattern}` : ""}</p><p className="mt-3 text-xs font-semibold uppercase tracking-wider text-slate-400">{detection.visibility_status.replace(/_/g, " ")}</p>{detection.uncertainty_explanation && <p className="mt-2 text-xs leading-5 text-amber-700">{detection.uncertainty_explanation}</p>}</div></button>{!disabled && <div className="flex gap-2 border-t border-slate-100 p-3"><Button variant="quiet" className="flex-1 px-2 py-2 text-xs" onClick={onToggle}><Pencil size={14} />{selected ? "Unselect" : "Select"}</Button><Button variant="danger" className="px-3 py-2" onClick={onReject} aria-label={`Reject ${detection.category}`}><Trash2 size={14} /></Button></div>}</div>;
}
