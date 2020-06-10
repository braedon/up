% rebase('base.tpl', title='up? - Link Down')
<main>
  <span class="spacer"></span>
  <form class="content limitWidth" action="/submit" method="POST">
    <h1>down!</h1>
    <div class="section">
      <p>
        That <a href="{{url}}" target="_blank" rel="noopener noreferrer">link</a>
        does seem to be down.
      </p>
      <p>Submit an email address to get notified when it's up.</p>
    </div>
    <div class="section">
      <input type="hidden" name="url" value="{{url}}">
      <input type="email" name="email" autocomplete="email" placeholder="Email Address" required>
      <button class="mainButton">Submit</button>
    </div>
  </form>
  <span class="spacer"></span>
  <div class="linkRow">
    <a href="/">Got another link?</a>
  </div>
</main>
