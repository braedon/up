% rebase('base.tpl', title='up?', description='Get notified when a link is back up.')
<main>
  <span class="spacer"></span>
  <form class="content limitWidth" action="/check" method="GET">
    <h1>up?</h1>
    <div class="section">
      <p>
        Got a link that's down?<br>
        Get notified when it's up.
      </p>
    </div>
    <div class="section">
      <input type="url" name="url" autocomplete="url" placeholder="Link URL" required>
      <button class="mainButton">Check Link</button>
    </div>
  </form>
  <span class="spacer"></span>
</main>
