insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'wardrobe-private',
  'wardrobe-private',
  false,
  26214400,
  array['image/jpeg']
)
on conflict (id) do update
set
  name = excluded.name,
  public = false,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;
