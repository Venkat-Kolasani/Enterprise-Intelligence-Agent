export function BrandMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <i />
      <i />
      <i />
    </span>
  )
}

export function BrandLockup({ inverse = false }) {
  return (
    <span className={`brand-lockup${inverse ? ' inverse' : ''}`}>
      <BrandMark />
      <span>metric<span>thread</span></span>
    </span>
  )
}
