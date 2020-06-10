% rebase('base.tpl', title='up?', description='Get notified when a link is back up.')
<div id="content">
  <h1>up?</h1>
  <div class="message">
    Got a link that's down?<br />
    We'll notify you when it's up.
  </div>
  <form action="/check" method="GET">
    <input type="url" name="url" autocomplete="url" placeholder="url" required/>
    <button>Check</button>
  </form>
</div>
