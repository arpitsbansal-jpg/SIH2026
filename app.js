/* RETINOVA — vanilla JS */

// ======================================================
// INITIALIZATION
// ======================================================

document.addEventListener('DOMContentLoaded', () => {

  // Scroll reveal
  const io = new IntersectionObserver(
    es =>
      es.forEach(
        e =>
          e.isIntersecting &&
          e.target.classList.add('in')
      ),
    { threshold: 0.12 }
  );

  document
    .querySelectorAll('.reveal')
    .forEach(el => io.observe(el));


  // Animated counters
  document
    .querySelectorAll('[data-count]')
    .forEach(el => {

      const target =
        parseFloat(el.dataset.count);

      const dec =
        el.dataset.dec ? 1 : 0;

      let n = 0;

      const step =
        target / 60;

      const t =
        setInterval(() => {

          n += step;

          if (n >= target) {
            n = target;
            clearInterval(t);
          }

          el.textContent =
            n.toFixed(dec) +
            (el.dataset.suffix || '');

        }, 20);
    });


  // Main features
  initScreening();
  initAuth();
  initPatientPortal();

});


// ======================================================
// SCREENING FLOW
// ======================================================

function initScreening() {

  const start =
    document.getElementById('startBtn');

  const screening =
    document.getElementById('screening');

  if (!start || !screening) {
    return;
  }


  // Start screening button
  start.addEventListener('click', () => {

    screening.classList.remove(
      'hidden'
    );

    screening.scrollIntoView({
      behavior: 'smooth'
    });

  });


  const input =
    document.getElementById(
      'fileInput'
    );

  const choose =
    document.getElementById(
      'chooseBtn'
    );

  const drop =
    document.getElementById(
      'dropzone'
    );

  const stepPreview =
    document.getElementById(
      'stepPreview'
    );

  const stepDone =
    document.getElementById(
      'stepDone'
    );

  const uploadBtn =
    document.getElementById(
      'uploadBtn'
    );

  const bar =
    document.getElementById(
      'bar'
    );

  const progressWrap =
    document.getElementById(
      'progressWrap'
    );

  const statusText =
    document.getElementById(
      'uploadStatus'
    );

  const doneNote =
    stepDone.querySelector(
      '.note'
    );

  let current = null;


  // ------------------------------------------------------
  // Choose image
  // ------------------------------------------------------

  choose.addEventListener(
    'click',
    () => input.click()
  );

  input.addEventListener(
    'change',
    e =>
      handle(
        e.target.files[0]
      )
  );


  // ------------------------------------------------------
  // Drag and drop
  // ------------------------------------------------------

  ['dragover', 'dragenter']
    .forEach(ev => {

      drop.addEventListener(
        ev,
        e => {

          e.preventDefault();

          drop.classList.add(
            'drag'
          );

        }
      );

    });


  ['dragleave', 'drop']
    .forEach(ev => {

      drop.addEventListener(
        ev,
        e => {

          e.preventDefault();

          drop.classList.remove(
            'drag'
          );

        }
      );

    });


  drop.addEventListener(
    'drop',
    e =>
      handle(
        e.dataTransfer.files[0]
      )
  );


  // ------------------------------------------------------
  // File size helper
  // ------------------------------------------------------

  function size(bytes) {

    return bytes <
      1024 * 1024

      ? (
          bytes / 1024
        ).toFixed(1) + ' KB'

      : (
          bytes / 1048576
        ).toFixed(2) + ' MB';
  }


  // ------------------------------------------------------
  // Handle selected image
  // ------------------------------------------------------

  function handle(file) {

    if (!file) {
      return;
    }


    // Validate file type
    if (
      ![
        'image/jpeg',
        'image/jpg',
        'image/png'
      ].includes(file.type)
    ) {

      alert(
        'Accepted formats: JPG, JPEG, PNG'
      );

      return;
    }


    const url =
      URL.createObjectURL(file);

    const img =
      new Image();


    img.onload = () => {

      current = {
        file,
        name: file.name,
        size: size(file.size),
        w: img.naturalWidth,
        h: img.naturalHeight,
        url
      };


      document.getElementById(
        'pvImg'
      ).src = url;


      document.getElementById(
        'mName'
      ).textContent =
        current.name;


      document.getElementById(
        'mSize'
      ).textContent =
        current.size;


      document.getElementById(
        'mW'
      ).textContent =
        current.w + ' px';


      document.getElementById(
        'mH'
      ).textContent =
        current.h + ' px';


      stepDone.classList.add(
        'hidden'
      );

      progressWrap.classList.add(
        'hidden'
      );

      bar.style.width =
        '0%';


      uploadBtn.disabled =
        false;

      uploadBtn
        .querySelector('span')
        .textContent =
        'Upload Image';


      stepPreview.classList.remove(
        'hidden'
      );


      stepPreview.scrollIntoView({
        behavior: 'smooth',
        block: 'center'
      });

    };


    img.onerror = () => {

      URL.revokeObjectURL(url);

      alert(
        'The selected file could not be read as an image.'
      );

    };


    img.src = url;

  }


  // ------------------------------------------------------
  // Upload image
  // ------------------------------------------------------

  uploadBtn.addEventListener(
    'click',
    () => {

      if (!current) {
        return;
      }


      uploadBtn.disabled =
        true;

      uploadBtn
        .querySelector('span')
        .textContent =
        'Uploading...';


      progressWrap.classList.remove(
        'hidden'
      );


      statusText.textContent =
        'Sending image to RETINOVA server...';


      bar.style.width =
        '0%';


      // Real HTTP upload
      const request =
        new XMLHttpRequest();


      request.open(
        'POST',
        '/api/upload'
      );


      // Upload progress
      request.upload.addEventListener(
        'progress',
        event => {

          if (
            event.lengthComputable
          ) {

            const percent =
              Math.round(
                (
                  event.loaded /
                  event.total
                ) * 100
              );


            bar.style.width =
              percent + '%';


            statusText.textContent =
              'Uploading... ' +
              percent +
              '%';

          }

        }
      );


      // Server response
      request.onload = () => {

        let response = null;


        try {

          response =
            JSON.parse(
              request.responseText
            );

        } catch (error) {

          response = null;

        }


        if (
          request.status >= 200 &&
          request.status < 300 &&
          response
        ) {

          bar.style.width =
            '100%';

          statusText.textContent =
            'Transfer complete';


          showDone(
            response
          );

          return;
        }


        const message =
          response?.detail ||
          'Upload failed. Please check that the RETINOVA server is running.';


        statusText.textContent =
          message;


        uploadBtn.disabled =
          false;


        uploadBtn
          .querySelector('span')
          .textContent =
          'Try Again';


        alert(message);

      };


      // Connection error
      request.onerror = () => {

        statusText.textContent =
          'Could not connect to the RETINOVA server.';


        uploadBtn.disabled =
          false;


        uploadBtn
          .querySelector('span')
          .textContent =
          'Try Again';


        alert(
          'Could not connect to the RETINOVA server. Start the backend with start.bat.'
        );

      };


      // Send actual image
      const formData =
        new FormData();


      formData.append(
        'file',
        current.file
      );


      request.send(
        formData
      );

    }
  );


  // ------------------------------------------------------
  // Show upload result
  // ------------------------------------------------------

  function showDone(response) {

    document.getElementById(
      'dName'
    ).textContent =
      response.filename;


    document.getElementById(
      'dSize'
    ).textContent =
      size(
        response.file_size
      );


    document.getElementById(
      'dDim'
    ).textContent =
      response.width +
      ' × ' +
      response.height +
      ' px';


    document.getElementById(
      'dImg'
    ).src =
      current.url;


    document.getElementById(
      'dTime'
    ).textContent =
      new Date().toLocaleString();


    // Store the REAL server result
    localStorage.setItem(
      'retinova_latest_screening',
      JSON.stringify(response)
    );


    // Show quality + AI information
    if (
      response.ai_prediction
    ) {

      doneNote.textContent =
        response.quality_message +
        ' AI prediction: ' +
        response.ai_prediction +
        ' with ' +
        response.ai_confidence +
        '% confidence.';

    } else {

      doneNote.textContent =
        response.quality_message +
        ' AI status: ' +
        response.ai_status +
        '.';

    }


    stepPreview.classList.add(
      'hidden'
    );


    stepDone.classList.remove(
      'hidden'
    );


    stepDone.scrollIntoView({
      behavior: 'smooth',
      block: 'center'
    });

  }


  // ------------------------------------------------------
  // Upload another image
  // ------------------------------------------------------

  document
    .getElementById(
      'againBtn'
    )
    .addEventListener(
      'click',
      () => {

        if (current?.url) {

          URL.revokeObjectURL(
            current.url
          );

        }


        current = null;

        input.value = '';

        bar.style.width =
          '0%';

        progressWrap.classList.add(
          'hidden'
        );

        stepDone.classList.add(
          'hidden'
        );

        stepPreview.classList.add(
          'hidden'
        );

        uploadBtn.disabled =
          false;

        uploadBtn
          .querySelector('span')
          .textContent =
          'Upload Image';


        drop.scrollIntoView({
          behavior: 'smooth',
          block: 'center'
        });

      }
    );

}


// ======================================================
// AUTHENTICATION
// ======================================================

function initAuth() {

  const tabs =
    document.querySelectorAll(
      '.tabs button'
    );

  let mode =
    'login';


  // Login / Signup tabs
  if (tabs.length) {

    tabs.forEach(button => {

      button.addEventListener(
        'click',
        () => {

          mode =
            button.dataset.mode;


          tabs.forEach(x =>
            x.classList.remove(
              'on'
            )
          );


          button.classList.add(
            'on'
          );


          document
            .getElementById(
              'signupOnly'
            )
            .classList.toggle(
              'hidden',
              mode !== 'signup'
            );


          document
            .getElementById(
              'authSubmit'
            )
            .querySelector('span')
            .textContent =
              mode === 'signup'
                ? 'Create Account'
                : 'Sign In';

        }
      );

    });

  }


  const form =
    document.getElementById(
      'authForm'
    );


  if (form) {

    form.addEventListener(
      'submit',
      async event => {

        event.preventDefault();


        const email =
          document
            .getElementById('email')
            .value
            .trim();


        const password =
          document
            .getElementById('pw')
            .value;


        const role =
          document
            .getElementById('role')
            .value;


        const fullname =
          document
            .getElementById(
              'fullname'
            )
            ?.value
            .trim() ||
          '';


        const submitButton =
          document.getElementById(
            'authSubmit'
          );


        const originalText =
          submitButton
            .querySelector('span')
            .textContent;


        submitButton.disabled =
          true;


        submitButton
          .querySelector('span')
          .textContent =
            mode === 'signup'
              ? 'Creating...'
              : 'Signing in...';


        const endpoint =
          mode === 'signup'
            ? '/api/auth/signup'
            : '/api/auth/login';


        const body =
          mode === 'signup'
            ? {
                full_name:
                  fullname,
                email,
                password,
                role
              }
            : {
                email,
                password
              };


        try {

          const response =
            await fetch(
              endpoint,
              {
                method: 'POST',
                headers: {
                  'Content-Type':
                    'application/json'
                },
                body:
                  JSON.stringify(
                    body
                  )
              }
            );


          const data =
            await response.json();


          if (!response.ok) {

            throw new Error(
              data.detail ||
              'Request failed.'
            );

          }


          localStorage.setItem(
            'retinova_user',
            JSON.stringify(
              data.user
            )
          );


          location.href =
            data.user.role +
            '.html';

        } catch (error) {

          alert(
            error.message ||
            'Could not connect to the RETINOVA server.'
          );


          submitButton.disabled =
            false;


          submitButton
            .querySelector('span')
            .textContent =
            originalText;

        }

      }
    );

  }


  // ------------------------------------------------------
  // Display logged-in user
  // ------------------------------------------------------

  const who =
    document.getElementById(
      'whoami'
    );


  if (who) {

    const u =
      JSON.parse(
        localStorage.getItem(
          'retinova_user'
        ) || 'null'
      );


    who.textContent =
      u
        ? u.name + ' · ' + u.role
        : 'guest session';

  }


  // ------------------------------------------------------
  // Logout
  // ------------------------------------------------------

  const out =
    document.getElementById(
      'logout'
    );


  if (out) {

    out.addEventListener(
      'click',
      async event => {

        event.preventDefault();


        try {

          await fetch(
            '/api/auth/logout',
            {
              method: 'POST'
            }
          );

        } finally {

          localStorage.removeItem(
            'retinova_user'
          );


          location.href =
            'login.html';

        }

      }
    );

  }

}


// ======================================================
// PATIENT PORTAL
// ======================================================

function initPatientPortal() {

  const patientGrade =
    document.getElementById(
      'patientGrade'
    );


  // Not on patient.html
  if (!patientGrade) {
    return;
  }


  const saved =
    localStorage.getItem(
      'retinova_latest_screening'
    );


  // No screening performed yet
  if (!saved) {
    return;
  }


  let data = null;


  try {

    data =
      JSON.parse(
        saved
      );

  } catch (error) {

    console.error(
      'Could not read screening result:',
      error
    );

    return;

  }


  if (!data) {
    return;
  }


  // ------------------------------------------------------
  // Prediction
  // ------------------------------------------------------

  const prediction =
    document.getElementById(
      'patientPrediction'
    );


  if (
    prediction &&
    data.ai_prediction
  ) {

    prediction.textContent =
      data.ai_prediction;

  }


  // ------------------------------------------------------
  // Grade badge
  // ------------------------------------------------------

  if (
    data.ai_prediction
  ) {

    patientGrade.textContent =
      data.ai_prediction;

  }


  // ------------------------------------------------------
  // Confidence
  // ------------------------------------------------------

  const confidence =
    document.getElementById(
      'patientConfidence'
    );


  if (
    confidence &&
    data.ai_confidence !== undefined
  ) {

    confidence.textContent =
      data.ai_confidence +
      '%';

  }


  // ------------------------------------------------------
  // Referable DR
  // ------------------------------------------------------

  const referable =
    document.getElementById(
      'patientReferable'
    );


  if (
    referable &&
    data.referable_dr !== undefined
  ) {

    referable.textContent =
      data.referable_dr
        ? 'Yes'
        : 'No';

  }


  // ------------------------------------------------------
  // Referable probability
  // ------------------------------------------------------

  const referableProbability =
    document.getElementById(
      'patientReferableProbability'
    );


  if (
    referableProbability &&
    data.referable_probability !==
      undefined
  ) {

    referableProbability.textContent =
      data.referable_probability +
      '%';

  }


  // ------------------------------------------------------
  // Image quality
  // ------------------------------------------------------

  const quality =
    document.getElementById(
      'patientQuality'
    );


  if (
    quality &&
    data.quality
  ) {

    quality.textContent =
      data.quality;

  }


  // ------------------------------------------------------
  // Patient-friendly summary
  // ------------------------------------------------------

  const summary =
    document.getElementById(
      'patientSummary'
    );


  if (
    summary &&
    data.ai_prediction
  ) {

    if (data.referable_dr) {

      summary.textContent =
        'The AI screening classified this image as ' +
        data.ai_prediction +
        ' and marked it as referable. ' +
        'A doctor should review the result.';

    } else {

      summary.textContent =
        'The AI screening classified this image as ' +
        data.ai_prediction +
        ' and did not mark it as referable.';

    }

  }


  // ------------------------------------------------------
  // Real Grad-CAM explanation
  // ------------------------------------------------------

  const explanation =
    document.getElementById(
      'patientExplanation'
    );

  if (
    explanation &&
    data.explanation_url
  ) {

    explanation.src =
      data.explanation_url +
      '?t=' +
      Date.now();

    explanation.alt =
      'Grad-CAM explanation of the latest AI screening';
  }


  // ------------------------------------------------------
  // Screening history
  // ------------------------------------------------------

  const historyGrade =
    document.getElementById(
      'historyGrade'
    );


  if (
    historyGrade &&
    data.ai_prediction
  ) {

    historyGrade.textContent =
      data.ai_prediction;

  }

}